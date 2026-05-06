const LIMIT = 10;

async function loadPosts(){

const res = await fetch("data/posts.json");
const data = await res.json();

const posts = data
.sort((a,b)=>new Date(b.date)-new Date(a.date))
.slice(0,LIMIT);

render(posts);

}

function getMedia(id){

const num = id.split("/")[1];

const images = [
`media/${num}.jpg`,
`media/${num}.png`,
`media/${num}.webp`
];

const videos = [
`media/${num}.mp4`
];

for(let img of images){
return `<img src="${img}" onerror="this.remove()">`
}

for(let vid of videos){
return `<video controls src="${vid}" onerror="this.remove()"></video>`
}

return ""

}

function render(posts){

const html = posts.map(p=>`

<div class="post">

<div class="meta">
${p.date} | ${p.views} views
</div>

<div class="text">
${p.text || ""}
</div>

${getMedia(p.id)}

<div style="margin-top:10px">
<a href="${p.link}" target="_blank">
مشاهده در تلگرام
</a>
</div>

</div>

`).join("")

document.getElementById("posts").innerHTML = html

}

loadPosts()

setInterval(loadPosts,30000)
