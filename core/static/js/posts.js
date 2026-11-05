/* Лента постов: посты людей, с которыми у вас есть пара, и ваши собственные. */
(async function () {
  const list = document.getElementById("list"), empty = document.getElementById("empty"), slot = document.getElementById("composer");
  const check = () => { empty.hidden = list.querySelector(".post") !== null; };

  slot.appendChild(DMPeople.composer(() => { reload(); DM.toast("Пост опубликован"); }));

  async function reload() {
    try {
      const { posts } = await DM.api("/api/posts/");
      list.textContent = "";
      posts.forEach(p => list.appendChild(DMPeople.postEl(p, { author: p.author, canDelete: p.author.mine, onDelete: check })));
      check();
    } catch (e) { DM.toast(e.message, "error"); }
  }
  reload();
})();
