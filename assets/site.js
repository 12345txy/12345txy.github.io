document.documentElement.classList.add('js');

const languageButton = document.getElementById('language');
const portrait = document.querySelector('.portrait-ring img');
const englishAlt = portrait.alt;

function showLanguage(language) {
  const chinese = language === 'zh-CN';
  document.documentElement.lang = chinese ? 'zh-CN' : 'en';
  languageButton.setAttribute('aria-label', chinese ? 'Switch to English' : '切换到中文');
  portrait.alt = chinese ? portrait.dataset.altZh : englishAlt;
  document.querySelector('nav').setAttribute('aria-label', chinese ? '主导航' : 'Main navigation');
  document.querySelector('.filters').setAttribute('aria-label', chinese ? '论文类型' : 'Publication type');
}
try {
  showLanguage(localStorage.getItem('homepage-language'));
} catch {
  showLanguage('en');
}
languageButton.addEventListener('click', () => {
  const next = document.documentElement.lang === 'en' ? 'zh-CN' : 'en';
  showLanguage(next);
  try { localStorage.setItem('homepage-language', next); } catch { /* Storage is optional. */ }
});

const filters = document.querySelectorAll('[data-filter]');
const papers = document.querySelectorAll('.paper');
for (const button of filters) {
  button.addEventListener('click', () => {
    for (const item of filters) item.setAttribute('aria-pressed', String(item === button));
    for (const paper of papers) {
      paper.hidden = button.dataset.filter !== 'all' && button.dataset.filter !== paper.dataset.type;
    }
    highlightSection();
  });
}

const navigation = Array.from(document.querySelectorAll('nav a'));
const sections = navigation.map(link => document.querySelector(link.hash));
function highlightSection() {
  let active = sections[0];
  const threshold = document.querySelector('header').offsetHeight + 35;
  for (const section of sections) {
    if (section.getBoundingClientRect().top <= threshold) active = section;
  }
  if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2) {
    active = sections[sections.length - 1];
  }
  for (const link of navigation) {
    if (link.hash === '#' + active.id) link.setAttribute('aria-current', 'location');
    else link.removeAttribute('aria-current');
  }
}
let framePending = false;
window.addEventListener('scroll', () => {
  if (framePending) return;
  framePending = true;
  requestAnimationFrame(() => { highlightSection(); framePending = false; });
}, {passive: true});
window.addEventListener('resize', highlightSection);
highlightSection();
