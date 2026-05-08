// تنظیمات - تشخیص مسیر صحیح
let postsData = null;
let currentChannel = null;

// تشخیص محیط (GitHub Pages یا لوکال)
const isGitHubPages = window.location.hostname.includes('github.io');
const basePath = isGitHubPages ? '/telegram-mirror' : '';

// بارگذاری دیتا از فایل JSON با مسیر صحیح
async function loadData() {
    try {
        // در GitHub Pages، فایل posts.json در ریشه پروژه است
        const jsonPath = isGitHubPages ? '../posts.json' : '../posts.json';
        
        console.log('Loading from:', jsonPath);
        
        const response = await fetch(jsonPath);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        postsData = await response.json();
        console.log('Data loaded:', postsData);
        return true;
    } catch (error) {
        console.error('Error loading data:', error);
        showError('خطا در بارگذاری داده‌ها: ' + error.message + '<br>لطفاً ابتدا mirror.py را اجرا کنید.');
        return false;
    }
}

// نمایش خطا
function showError(message) {
    const container = document.getElementById('postsContainer');
    container.innerHTML = `
        <div class="error">
            <p>❌ ${message}</p>
            <p>راه حل:</p>
            <ol>
                <li>ابتدا mirror.py را اجرا کنید: <code>python mirror.py</code></li>
                <li>صبر کنید تا GitHub Actions اجرا شود</li>
                <li>سپس صفحه را رفرش کنید</li>
            </ol>
        </div>
    `;
}

// پر کردن لیست کانال‌ها
function populateChannels() {
    const select = document.getElementById('channelSelect');
    select.innerHTML = '<option value="">انتخاب کانال...</option>';
    
    if (!postsData || !postsData.channels) {
        select.innerHTML = '<option value="">هیچ کانالی یافت نشد</option>';
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
            // مسیر صحیح برای فایل‌های media
            const mediaUrl = isGitHubPages ? `../media/${media.file}` : `../media/${media.file}`;
            
            if (media.type === 'image') {
                const img = document.createElement('img');
                img.src = mediaUrl;
                img.alt = 'تصویر';
                img.loading = 'lazy';
                img.className = 'media-image';
                img.onerror = () => {
                    console.error('Failed to load image:', mediaUrl);
                    img.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 24 24" fill="none" stroke="%23999" stroke-width="2"%3E%3Crect x="3" y="3" width="18" height="18" rx="2"%3E%3C/rect%3E%3Ccircle cx="8.5" cy="8.5" r="1.5"%3E%3C/circle%3E%3Cpath d="M21 15l-5-4-3 3-4-4-5 5"%3E%3C/path%3E%3C/svg%3E';
                };
                img.onclick = () => openLightbox(mediaUrl);
                mediaDiv.appendChild(img);
            } else if (media.type === 'video') {
                const video = document.createElement('video');
                video.src = mediaUrl;
                video.controls = true;
                video.className = 'media-video';
                video.preload = 'metadata';
                video.onerror = () => {
                    console.error('Failed to load video:', mediaUrl);
                };
                mediaDiv.appendChild(video);
            }
        });
        
        div.appendChild(mediaDiv);
    }
    
    return div;
}

// فرمت تاریخ به فارسی
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

// نمایش وضعیت بروزرسانی
function showLastUpdate() {
    const lastUpdateSpan = document.getElementById('lastUpdate');
    if (lastUpdateSpan && postsData && postsData.last_update) {
        lastUpdateSpan.textContent = formatDate(postsData.last_update);
    }
}

// بارگذاری اولیه
async function init() {
    console.log('Initializing viewer...');
    const success = await loadData();
    if (success) {
        populateChannels();
        showLastUpdate();
    }
}

// اجرا پس از بارگذاری کامل صفحه
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
