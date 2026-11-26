---
title: 评测分数别急着信：一次 vLLM 前缀缓存导致的静默错误
date: 2026-11-26
summary: 多轮 Agent 评测里，模型在第二轮突然“忘了任务”，却没有任何报错。用 cache_salt 做对照、抓真实请求重放，最终定位到解码阶段写入的缓存块。
tags: vLLM, Inference, Evaluation, Debugging
lang: zh
draft: false
---

> **TL;DR** 在 vLLM 上同时开启前缀缓存（prefix caching）和 MTP 投机解码，服务一个 Mamba + Attention 混合架构的模型时，**解码阶段写入缓存的块**会带着错误状态被后续请求复用。结果是多轮 Agent 在第二轮开始“忘记任务”，而日志里没有任何报错。修复方式是只缓存 prompt 部分的块。

## 背景

我在做代码 Agent 的多轮评测：模型每一轮都会收到“系统提示 + 任务描述 + 之前所有轮次的对话和工具输出”，上下文动辄几万 token。这类负载天然适合前缀缓存：第 *n* 轮的 prompt 几乎完整包含第 *n−1* 轮的内容，命中缓存可以省掉绝大部分 prefill。

服务配置大致是：

- 推理框架：vLLM 0.23
- 模型：开源的 Mamba + Attention 混合架构模型（这类模型的前缀缓存走实验性的 Mamba `align` 模式，vLLM 启动时会打一条 warning）
- 开启 `--enable-prefix-caching`，并使用 MTP 投机解码

## 现象：模型“忘了任务”，但什么都没报错

翻轨迹时发现一个奇怪的模式：第一轮模型明明理解了任务、开始读代码，第二轮却说出类似 *“用户还没有给我任何任务”* 的话，然后开始漫无目的地探索。

这种错误非常隐蔽：

- 服务端没有异常，请求全部 200；
- 评测脚本只看最终分数，只会表现为“这个模型分数偏低”；
- 单看任何一条轨迹，都可能被当成模型能力问题。

## 第一步：先排除 prompt 本身的问题

最直接的怀疑是客户端拼 prompt 出了错，比如截断或丢了任务描述。用 vLLM 的 `/v1/chat/completions/render` 接口把实际送进模型的 prompt 渲染出来，任务描述完整地在里面。prompt 没问题。

## 第二步：用 `cache_salt` 做对照

vLLM 支持在请求里带 `cache_salt`：salt 不同的请求不会共享前缀缓存。这就得到了一个干净的对照实验——**同一个请求，唯一的区别是是否命中缓存**：

```python
import requests

def ask(body, salt=None):
    if salt:
        body = {**body, "cache_salt": salt}
    r = requests.post(f"{BASE}/v1/chat/completions", json=body, timeout=600)
    return r.json()["choices"][0]["message"]["content"]

# body = 抓到的一个真实的第二轮请求
hit  = [ask(body) for _ in range(11)]                              # 命中缓存
cold = [ask(body, salt=f"fresh-{i}") for i in range(11)]          # 强制不命中
```

结果：

| 条件 | “没有任务”的比例 |
|---|---|
| 命中前缀缓存 | 6 / 11 |
| 新 salt（不命中） | 0 / 11 |

prompt 完全相同，只差在缓存，结论很明确：**问题出在前缀缓存**。

## 第三步：合成实验复现失败

接下来想用合成数据稳定复现：长单轮/两轮对话、并发共享前缀、制造 KV 压力触发驱逐……开和不开 MTP 都试了，**全部正常**。

这一步很容易让人以为“是偶发、可以忽略”。但回头看，合成实验的问题在于没有覆盖真实负载的关键特征。

## 第四步：抓真实请求，按“缓存来自哪里”分组重放

于是换了思路：在评测链路里把每一轮的请求体原样落盘，然后对出问题的那一轮做重放，并**控制缓存里的内容是怎么来的**：

| 缓存来源 | 丢任务的比例 |
|---|---|
| 冷启动（新 salt） | 0 / 4 |
| 只命中 prompt 阶段写入的块 | 0 / 4 |
| 命中**上一轮解码时**写入的块 | 4 / 4 |

关键就在第三行：上一轮模型生成的输出，会在解码过程中被逐块写进前缀缓存；下一轮请求的 prompt 恰好包含这段输出，于是命中了这些块。**解码阶段完成的块带着错误的状态**（推测与 MTP 投机解码和 Mamba `align` 模式的状态对齐有关），复用它们就会污染下一轮的上下文。

这也解释了合成实验为什么没复现：短对话里，解码写入的块很少被下一轮命中。

## 修复：只缓存 prompt 块

既然问题只出在“解码阶段写入的块”，最小的修复就是让前缀缓存只登记 prompt 部分的块：把 `KVCacheCoordinator.cache_blocks` 的 token 数截断到 `num_prompt_tokens`。

为了不改动共享的 vLLM 安装，我用 `sitecustomize.py` 写了一个 import hook，只在设置了环境变量的进程里生效：

```python
# sitecustomize.py —— 放进 PYTHONPATH，并设置 VLLM_PREFIX_CACHE_PROMPT_ONLY=1
import importlib.abc, importlib.machinery, os, sys

_TARGET = "vllm.v1.core.kv_cache_coordinator"

def _patch(mod):
    for obj in list(vars(mod).values()):
        if isinstance(obj, type) and "cache_blocks" in vars(obj) and obj.__module__ == _TARGET:
            orig = vars(obj)["cache_blocks"]
            def cache_blocks(self, request, num_computed_tokens, _orig=orig):
                # 只把 prompt 部分登记进前缀缓存，解码产生的块不缓存
                return _orig(self, request, min(num_computed_tokens, request.num_prompt_tokens))
            obj.cache_blocks = cache_blocks

class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name != _TARGET:
            return None
        sys.meta_path.remove(self)
        spec = importlib.machinery.PathFinder.find_spec(name, path)
        load = spec.loader.exec_module
        def exec_and_patch(module):
            load(module)
            _patch(module)
        spec.loader.exec_module = exec_and_patch
        return spec

if os.environ.get("VLLM_PREFIX_CACHE_PROMPT_ONLY") == "1":
    sys.meta_path.insert(0, _Finder())
```

代价很小：每一轮需要多 prefill 一次上一轮的输出（通常约 1k token），而几万 token 的历史前缀依然能命中缓存。

用规则扫描轨迹也印证了这一点：开着缓存的批次里，有 4 / 53 个会话出现“没有任务”的话术；关闭缓存的 226 个会话里是 0。

## 经验

1. **推理优化不保证数值等价。** 前缀缓存、投机解码、量化 KV 这些优化，上线前至少用开/关对照验证一次输出分布，尤其是新架构（混合注意力、状态空间模型）配上实验性特性的时候。
2. **给静默错误装“探针”。** 分数只是最后一层信号。针对已知症状写规则扫描轨迹（比如搜“用户没有给任务”这类话术），能把“分数偏低”变成可计数的异常。
3. **`cache_salt` 是很好用的对照工具。** 它让你在不改服务配置的前提下，对同一个请求做“命中/不命中”的 A/B。
4. **合成复现失败 ≠ 没有问题。** 把真实请求原样落盘并重放，比设计合成用例更快逼近真实的触发条件。
5. **修复先做最小侵入。** 用环境变量开关的 import hook，不动共享安装，出问题可以一键回退。

*注：以上基于 vLLM 0.23，后续版本可能已经修复。*
