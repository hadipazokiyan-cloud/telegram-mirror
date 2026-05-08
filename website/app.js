// تنظیمات
let postsData = null;
let currentChannel = null;

// بارگذاری دیتا از فایل JSON
async function loadData() {
    try {
        const response = await fetch('../posts.json');
        if (!response.ok) {
            throw new Error('نمیتوان فایل posts.json را بارگذاری کرد');
        }
        postsData = await response.json();
        return true;
    } catch (error) {
        console.error('خطا:', error);
        showError('خطا در بارگذاری داده‌ها: ' + error.message);
        return false;
    }
}

// نمایش خطا
function showError(message) {
    const container = document.getElementById('postsContainer');
    container.innerHTML = `
        <div class="error">
            <p>❌ ${message}</p>
            <p>لطفاً ابتدا mirror.py را اجرا کنید.</p>
        </div>
    `;
}

// پر کردن لیست کانال‌ها
function populateChannels() {
    const select = document.getElementById('channelSelect');
    select.innerHTML = '<option value="">انتخاب کانال...</option>';
    
    if (!postsData || !postsData.channels) {
        return;
    }
    
    const channels = Object.keys(postsData.channels);
    
    if (channels.length === 0) {
        select.innerHTML = '<option value="">هیچ کانالی یافت نشد</option>';
        return;
    }
    
    channels.forEach(channel => {
        const option = document.createElement('option');
        option.value = channel;
        option.textContent = `@${channel}`;
        select.appendChild(option);
    });
    
    // انتخاب اولین کانال به صورت خودکار
    if (channels.length > 0) {
        select.value = channels[0];
        loadChannel(channels[0]);
    }
}

// بارگذاری پست‌های یک کانال
function loadChannel(channel) {
    currentChannel = channel;
    const container = document.getElementById('postsContainer');
    
    if (!postsData || !postsData.channels || !postsData.channels[channel]) {
        container.innerHTML = '<div class="error">پستی یافت نشد</div>';
        return;
    }
    
    const posts = postsData.channels[channel];
    
    if (posts.length === 0) {
        container.innerHTML = '<div class="empty">هیچ پستی در این کانال وجود ندارد</div>';
        return;
    }
    
    // نمایش پست‌ها
    container.innerHTML = '';
    
    // مرتب‌سازی از جدید به قدیم
    const sortedPosts = [...posts].sort((a, b) => b.id - a.id);
    
    sortedPosts.forEach(post => {
        const postElement = createPostElement(post, channel);
        container.appendChild(postElement);
    });
}

// ساخت المان پست
function createPostElement(post, channel) {
    const div = document.createElement('div');
    div.className = 'post';
    div.setAttribute('data-id', post.id);
    
    // هدر پست
    const header = document.createElement('div');
    header.className = 'post-header';
    header.innerHTML = `
        <span class="channel-name">@${channel}</span>
        <span class="post-id">پست ${post.id}</span>
        <span class="post-date">${formatDate(post.date)}</span>
    `;
    div.appendChild(header);
    
    // متن پست
    if (post.text && post.text.trim()) {
        const textDiv = document.createElement('div');
        textDiv.className = 'post-text';
        textDiv.textContent = post.text;
        div.appendChild(textDiv);
    }
    
    // رسانه‌ها
    if (post.media && post.media.length > 0) {
        const mediaDiv = document.createElement('div');
        mediaDiv.className = 'post-media';
        
        post.media.forEach(media => {
            const mediaUrl = `../media/${media.file}`;
            
            if (media.type === 'image') {
                const img = document.createElement('img');
                img.src = mediaUrl;
                img.alt = 'تصویر';
                img.loading = 'lazy';
                img.className = 'media-image';
                img.onclick = () => openLightbox(mediaUrl);
                mediaDiv.appendChild(img);
            } else if (media.type === 'video') {
                const video = document.createElement('video');
                video.src = mediaUrl;
                video.controls = true;
                video.className = 'media-video';
                video.preload = 'metadata';
                mediaDiv.appendChild(video);
            }
        });
        
        div.appendChild(mediaDiv);
    }
    
    return div;
}

// فرمت تاریخ
function formatDate(dateString) {
    if (!dateString) return 'تاریخ نامشخص';
    
    try {
        const date = new Date(dateString);
        const persianDate = new Intl.DateTimeFormat('fa-IR', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        }).format(date);
        return persianDate;
    } catch {
        return dateString;
    }
}

// لایت‌باکس برای تصاویر
function openLightbox(imageUrl) {
    const lightbox = document.createElement('div');
    lightbox.className = 'lightbox';
    lightbox.onclick = () => lightbox.remove();
    
    const img = document.createElement('img');
    img.src = imageUrl;
    img.className = 'lightbox-image';
    
    lightbox.appendChild(img);
    document.body.appendChild(lightbox);
}

// رویدادها
document.getElementById('channelSelect').addEventListener('change', (e) => {
    if (e.target.value) {
        loadChannel(e.target.value);
    }
});

// بارگذاری اولیه
async function init() {
    const success = await loadData();
    if (success) {
        populateChannels();
    }
}

init();
