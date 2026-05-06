const POSTS_LIMIT = 15;   // فقط آخرین 15 پست

const container = document.getElementById("posts");
const searchInput = document.getElementById("search");

let allPosts = [];

function getMediaElement(postId) {
  const id = postId.split("/")[1];

  const extensions = ["jpg", "png", "jpeg", "webp", "mp4", "pdf"];

  for (let ext of extensions) {
    const path = `media/${id}.${ext}`;
    const xhr = new XMLHttpRequest();
    xhr.open("HEAD", path, false);
    try {
      xhr.send();
      if (xhr.status !== 404) {
        if (ext === "mp4") {
          return `<video controls src="${path}"></video>`;
        }
        if (ext === "pdf") {
          return `<a href="${path}" target="_blank">دانلود فایل</a>`;
        }
        return `<img src="${path}" />`;
      }
    } catch (e) {}
  }

  return "";
}

function render(posts) {
  container.innerHTML = posts.map(p => `
    <article class="post">
      <div class="meta">
        ${p.date || "-"} | بازدید: ${p.views || "-"}
      </div>
      <div>${p.text || ""}</div>
      ${getMediaElement(p.id)}
      <div>
        <a href="${p.link}" target="_blank">مشاهده در تلگرام</a>
      </div>
    </article>
  `).join("");
}

fetch("data/posts.json")
  .then(r => r.json())
  .then(data => {
    allPosts = data
      .sort((a, b) => new Date(b.date) - new Date(a.date))
      .slice(0, POSTS_LIMIT);

    render(allPosts);
  });

searchInput.addEventListener("input", () => {
  const value = searchInput.value.trim();
  if (!value) return render(allPosts);

  const filtered = allPosts.filter(p =>
    (p.text || "").includes(value)
  );

  render(filtered);
});
