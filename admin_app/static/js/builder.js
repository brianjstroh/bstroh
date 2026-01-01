/**
 * Website Builder - Shared utilities and helpers
 */

const Builder = {
  /**
   * Fetch wrapper with error handling
   */
  async fetch(url, options = {}) {
    try {
      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          ...options.headers
        },
        ...options
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || `HTTP ${response.status}`);
      }

      return data;
    } catch (error) {
      console.error('API Error:', error);
      throw error;
    }
  },

  /**
   * Upload a file and return the URL
   */
  async uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch('/builder/assets/upload', {
      method: 'POST',
      body: formData
    });

    const data = await response.json();

    if (!data.success) {
      throw new Error(data.error || 'Upload failed');
    }

    return data.url;
  },

  /**
   * Show a toast notification
   */
  toast(message, type = 'info') {
    const toastContainer = document.getElementById('toast-container') || this.createToastContainer();

    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-bg-${type} border-0 show`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
      <div class="d-flex">
        <div class="toast-body">${message}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
      </div>
    `;

    toastContainer.appendChild(toast);

    // Auto-dismiss after 3 seconds
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  },

  createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
    container.style.zIndex = '1100';
    document.body.appendChild(container);
    return container;
  },

  /**
   * Debounce function for live preview updates
   */
  debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  },

  /**
   * Generate a unique ID
   */
  generateId() {
    return 'comp_' + Math.random().toString(36).substr(2, 9);
  },

  /**
   * Slugify a string for URLs
   */
  slugify(text) {
    return text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '');
  },

  /**
   * Format bytes to human readable size
   */
  formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  },

  /**
   * Validate image file
   */
  validateImage(file, maxSizeMB = 5) {
    const validTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml'];

    if (!validTypes.includes(file.type)) {
      throw new Error('Invalid file type. Please upload an image (JPEG, PNG, GIF, WebP, or SVG).');
    }

    if (file.size > maxSizeMB * 1024 * 1024) {
      throw new Error(`File too large. Maximum size is ${maxSizeMB}MB.`);
    }

    return true;
  },

  /**
   * Color manipulation helpers
   */
  colors: {
    hexToRgb(hex) {
      const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
      return result ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16)
      } : null;
    },

    rgbToHex(r, g, b) {
      return '#' + [r, g, b].map(x => {
        const hex = x.toString(16);
        return hex.length === 1 ? '0' + hex : hex;
      }).join('');
    },

    lighten(hex, percent) {
      const rgb = this.hexToRgb(hex);
      if (!rgb) return hex;

      const amount = Math.round(255 * (percent / 100));
      const r = Math.min(255, rgb.r + amount);
      const g = Math.min(255, rgb.g + amount);
      const b = Math.min(255, rgb.b + amount);

      return this.rgbToHex(r, g, b);
    },

    darken(hex, percent) {
      const rgb = this.hexToRgb(hex);
      if (!rgb) return hex;

      const amount = Math.round(255 * (percent / 100));
      const r = Math.max(0, rgb.r - amount);
      const g = Math.max(0, rgb.g - amount);
      const b = Math.max(0, rgb.b - amount);

      return this.rgbToHex(r, g, b);
    }
  }
};

// Make it globally available
window.Builder = Builder;
