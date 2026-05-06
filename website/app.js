const postsContainer = document.getElementById("posts");
const searchInput = document.getElementById("search");

let allPosts = [];

async function loadPosts() {
    try {
        const response = await fetch("../posts.json");
        const data = await response.json();

        // مرتب سازی جدید به قدیم
        allPosts = data.sort((a, b) => b.id - a.id);

        renderPosts(allPosts.slice(0, 20));

    } catch (error) {
        postsContainer.innerHTML = "<p>خطا در بارگذاری پست‌ها</p>";
        console.error(error);
    }
}

function renderPosts(posts) {

    postsContainer.innerHTML = "";

    posts.forEach(post => {

        const postDiv = document.createElement("div");
        postDiv.className = "post";

        const date = new Date(post.date).toLocaleString();

        let mediaHTML = "";

        if (post.media) {

            if (post.media.type === "photo") {
                mediaHTML = `<img src="../media/${post.id}.jpg">`;
            }

            if (post.media.type === "video") {
                mediaHTML = `<video controls src="../media/${post.id}.mp4"></video>`;
            }

        }

        postDiv.innerHTML = `
            <div class="post-date">${date}</div>
            <div class="post-text">${post.text}</div>
            ${mediaHTML}
        `;

        postsContainer.appendChild(postDiv);

    });

}

searchInput.addEventListener("input", () => {

    const q = searchInput.value.toLowerCase();

    const filtered = allPosts.filter(p =>
        p.text && p.text.toLowerCase().includes(q)
    );

    renderPosts(filtered.slice(0, 20));

});

loadPosts();
