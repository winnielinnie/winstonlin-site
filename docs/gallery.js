(() => {
  const viewer = document.querySelector('.photo-viewer');
  if (!viewer || typeof viewer.showModal !== 'function') return;
  const links = [...document.querySelectorAll('[data-photo]')];
  const picture = viewer.querySelector('img');
  const count = viewer.querySelector('.viewer-count');
  let current = 0;
  let returnFocus;

  function show(index) {
    current = (index + links.length) % links.length;
    const link = links[current];
    picture.src = link.href;
    picture.alt = link.querySelector('img').alt;
    count.textContent = `${current + 1} / ${links.length}`;
  }

  links.forEach((link, index) => {
    link.addEventListener('click', event => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      returnFocus = link;
      show(index);
      viewer.showModal();
      document.body.classList.add('viewer-open');
    });
  });
  viewer.querySelector('[data-close]').addEventListener('click', () => viewer.close());
  viewer.querySelector('[data-previous]').addEventListener('click', () => show(current - 1));
  viewer.querySelector('[data-next]').addEventListener('click', () => show(current + 1));
  viewer.addEventListener('keydown', event => {
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
      event.preventDefault();
      show(current + (event.key === 'ArrowRight' ? 1 : -1));
    }
  });
  viewer.addEventListener('close', () => {
    document.body.classList.remove('viewer-open');
    returnFocus?.focus({preventScroll: true});
  });
})();
