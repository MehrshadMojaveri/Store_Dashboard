const numberFormat = new Intl.NumberFormat('fa-IR');
const pageNames = {
  dashboard: 'داشبورد',
  products: 'لیست محصولات',
  'add-product': 'افزودن محصول',
  stock: 'کاهش موجودی محصول',
  'add-stock': 'افزایش موجودی محصول',
  'sales-products': 'آمار فروش محصولات',
  'sales-count': 'تعداد فروش محصولات',
  settings: 'تنظیمات'
};

let products = [];
let sales = [];
let dashboardData = null;
let settings = null;
let searchTimeout;

const formatPrice = value => `${numberFormat.format(value || 0)} تومان`;
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
}[character]));

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body) headers.set('Content-Type', 'application/json');
  if (!['GET', 'HEAD'].includes((options.method || 'GET').toUpperCase())) {
    headers.set('X-CSRFToken', document.querySelector('meta[name="csrf-token"]').content);
  }
  const response = await fetch(path, {
    ...options,
    headers,
    credentials: 'same-origin'
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || 'خطا در ارتباط با سرور.');
  return payload;
}

function productRow(product) {
  const stockStatus = product.stock === 0
    ? ['cancel', 'ناموجود']
    : settings?.show_low_stock && product.stock < (settings?.low_stock_threshold ?? 5)
      ? ['pending', 'موجودی کم']
      : ['success', 'موجود'];
  return `<tr>
    <td><div class="table-product"><span class="product-thumb"><span class="material-symbols-rounded">${escapeHtml(product.icon)}</span></span><strong>${escapeHtml(product.name)}</strong></div></td>
    <td>${escapeHtml(product.category_name)}</td>
    <td>${formatPrice(product.price)}</td>
    <td>${numberFormat.format(product.stock)} عدد</td>
    <td><span class="status ${stockStatus[0]}">${stockStatus[1]}</span></td>
    <td><button class="icon-btn delete-product" data-id="${product.id}" title="حذف محصول" aria-label="حذف ${escapeHtml(product.name)}"><span class="material-symbols-rounded">delete</span></button></td>
  </tr>`;
}

function saleRow(sale) {
  const statusClass = {
    completed: 'success',
    pending: 'pending',
    cancelled: 'cancel'
  }[sale.status] || 'pending';
  const date = new Intl.DateTimeFormat('fa-IR', {
    dateStyle: 'medium',
    timeStyle: 'short'
  }).format(new Date(sale.created_at));
  return `<tr>
    <td><strong>#${escapeHtml(sale.order)}</strong></td>
    <td><div class="customer-cell"><span class="customer-avatar">${escapeHtml(sale.customer.slice(0, 1))}</span>${escapeHtml(sale.customer)}</div></td>
    <td><div class="table-product"><span class="product-thumb"><span class="material-symbols-rounded">${escapeHtml(sale.icon)}</span></span>${escapeHtml(sale.product)}</div></td>
    <td>${date}</td>
    <td><strong>${formatPrice(sale.total)}</strong></td>
    <td><span class="status ${statusClass}">${escapeHtml(sale.status_name)}</span></td>
  </tr>`;
}

function renderProducts(productRows = products) {
  const body = document.querySelector('#productsBody');
  body.innerHTML = productRows.map(productRow).join('');
  document.querySelector('#productsEmpty').classList.toggle('hidden', productRows.length > 0);
  document.querySelector('#stockProduct').innerHTML = products.map(product =>
    `<option value="${product.id}" ${product.stock === 0 ? 'disabled' : ''}>${escapeHtml(product.name)} - موجودی: ${numberFormat.format(product.stock)} عدد</option>`
  ).join('');
  document.querySelector('#increaseStockProduct').innerHTML = products.map(product =>
    `<option value="${product.id}">${escapeHtml(product.name)} - موجودی: ${numberFormat.format(product.stock)} عدد</option>`
  ).join('');
}

function renderSales() {
  document.querySelector('#recentSalesBody').innerHTML = sales.slice(0, 4).map(saleRow).join('');
  document.querySelector('#salesTableBody').innerHTML = sales.map(saleRow).join('');
  const topProducts = dashboardData.top_products;
  const totalUnits = topProducts.reduce((total, product) => total + product.units_sold, 0);
  document.querySelector('#salesProductsBody').innerHTML = topProducts.map((product, index) => {
    const share = totalUnits ? Math.round(product.units_sold / totalUnits * 100) : 0;
    return `<tr>
      <td><span class="rank">${numberFormat.format(index + 1)}</span></td>
      <td><div class="table-product"><span class="product-thumb"><span class="material-symbols-rounded">${escapeHtml(product.icon)}</span></span><strong>${escapeHtml(product.name)}</strong></div></td>
      <td>${numberFormat.format(product.units_sold)} عدد</td>
      <td><strong>${formatPrice(product.revenue)}</strong></td>
      <td><div style="min-width:120px"><div class="stock-progress"><span style="width:${share}%"></span></div><small>${numberFormat.format(share)}٪</small></div></td>
    </tr>`;
  }).join('');
  document.querySelector('#bestsellerCarousel').innerHTML = topProducts.slice(0, 3).map((product, index) =>
    `<article class="product-mini">
      <div class="product-image"><span class="material-symbols-rounded">${escapeHtml(product.icon)}</span></div>
      <div><strong>${escapeHtml(product.name)}</strong><small>${numberFormat.format(product.units_sold)} فروش</small><b>${formatPrice(product.price)}</b></div>
      <span class="rank">${numberFormat.format(index + 1)}</span>
    </article>`
  ).join('');
  if (window.jQuery && topProducts.length) {
    const carousel = window.jQuery('#bestsellerCarousel');
    if (!carousel.hasClass('owl-loaded')) {
      carousel.owlCarousel({
        rtl: true,
        items: 1,
        margin: 10,
        dots: true,
        nav: false,
        responsive: { 0: { items: 1 }, 600: { items: 2 }, 1000: { items: 2 } }
      });
    }
  }
}

function renderChart(days) {
  const width = 700;
  const baseline = 215;
  const peak = 25;
  const maxValue = Math.max(...days.map(day => day.revenue), 1);
  const points = days.map((day, index) => ({
    x: days.length > 1 ? index * width / (days.length - 1) : width / 2,
    y: baseline - (day.revenue / maxValue) * (baseline - peak)
  }));
  const line = points.map((point, index) => `${index ? 'L' : 'M'}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ');
  document.querySelector('#chartLinePath').setAttribute('d', line);
  document.querySelector('#chartFillPath').setAttribute('d', `${line} L${width},230 L0,230 Z`);
  const lastPoint = points[points.length - 1] || { x: 0, y: baseline };
  document.querySelector('#chartPoint').setAttribute('cx', lastPoint.x);
  document.querySelector('#chartPoint').setAttribute('cy', lastPoint.y);
  document.querySelector('#chartLabels').innerHTML = days.map((day, index) =>
    `<span>${index === days.length - 1 ? 'امروز' : new Intl.DateTimeFormat('fa-IR', { weekday: 'short' }).format(new Date(`${day.date}T12:00:00`))}</span>`
  ).join('');
  document.querySelectorAll('.chart-y-labels span').forEach((label, index) => {
    const value = maxValue * (4 - index) / 4;
    label.textContent = value >= 1000000
      ? `${numberFormat.format(Math.round(value / 1000000))}م`
      : numberFormat.format(Math.round(value));
  });
}

function renderDashboard() {
  const { stats, sales_by_day: days, top_products: topProducts } = dashboardData;
  document.querySelector('#totalProducts').textContent = numberFormat.format(stats.total_products);
  document.querySelector('#availableProducts').textContent = numberFormat.format(stats.available_products);
  document.querySelector('#outOfStockProducts').textContent = numberFormat.format(stats.out_of_stock_products);
  document.querySelector('#todayRevenue').textContent = numberFormat.format(stats.today_revenue);
  document.querySelector('#todayOrders').textContent = numberFormat.format(stats.today_orders);
  document.querySelector('#monthRevenue').textContent = numberFormat.format(stats.month_revenue);
  document.querySelector('#monthOrders').textContent = numberFormat.format(stats.month_orders);
  document.querySelector('#monthlyOrders').textContent = numberFormat.format(stats.month_orders);
  document.querySelector('#inventoryValue').textContent = numberFormat.format(stats.inventory_value);
  document.querySelector('#inventoryUnits').textContent = numberFormat.format(stats.inventory_units);
  const weeklyRevenue = days.reduce((total, day) => total + day.revenue, 0);
  document.querySelector('#weeklyRevenue').textContent = formatPrice(weeklyRevenue);
  document.querySelector('#weeklyOrders').textContent = `${numberFormat.format(days.reduce((total, day) => total + day.orders, 0))} سفارش`;
  const channelCount = stats.channels.reduce((total, channel) => total + channel.count, 0);
  const channelElementIds = { website: 'websiteSales', instagram: 'instagramSales', marketplace: 'marketplaceSales' };
  const channelCounts = { website: 0, instagram: 0, marketplace: 0 };
  for (const channel of stats.channels) {
    channelCounts[channel.channel] = channel.count;
    const element = document.getElementById(channelElementIds[channel.channel]);
    if (element) element.textContent = `${numberFormat.format(channelCount ? Math.round(channel.count / channelCount * 100) : 0)}٪`;
  }
  const websiteEnd = channelCount ? channelCounts.website / channelCount * 100 : 0;
  const instagramEnd = websiteEnd + (channelCount ? channelCounts.instagram / channelCount * 100 : 0);
  document.querySelector('.donut').style.background =
    `conic-gradient(#5969ed 0 ${websiteEnd}%, #4bbfd1 ${websiteEnd}% ${instagramEnd}%, #a16aec ${instagramEnd}% 100%)`;
  renderChart(days);
  document.querySelector('#topProductsEmpty')?.classList.toggle('hidden', topProducts.length > 0);
}

function renderSettings() {
  document.querySelector('#notificationsSetting').checked = settings.notifications_enabled;
  document.querySelector('#lowStockSetting').checked = settings.show_low_stock;
  document.querySelector('#lowStockDescription').textContent =
    `محصولات با موجودی کمتر از ${numberFormat.format(settings.low_stock_threshold)} عدد را مشخص کن.`;
}

function showToast(message, type = 'success') {
  const toast = document.createElement('div');
  toast.className = 'toast-message';
  const icon = document.createElement('span');
  icon.className = 'material-symbols-rounded';
  icon.textContent = type === 'success' ? 'check_circle' : 'info';
  const text = document.createElement('span');
  text.textContent = message;
  toast.append(icon, text);
  document.querySelector('#toastContainer').append(toast);
  setTimeout(() => toast.remove(), 3200);
}

async function refreshData() {
  const [productData, saleData, summary, storeSettings] = await Promise.all([
    api('/api/products/'),
    api('/api/sales/'),
    api('/api/dashboard/'),
    api('/api/settings/')
  ]);
  products = productData.results;
  sales = saleData.results;
  dashboardData = summary;
  settings = storeSettings;
  renderProducts();
  renderSales();
  renderDashboard();
  renderSettings();
}

function goToPage(page) {
  document.querySelectorAll('.page').forEach(element => element.classList.remove('active'));
  document.querySelector(`#${page}-page`)?.classList.add('active');
  document.querySelector('#pageTitle').textContent = pageNames[page] || 'داشبورد';
  document.querySelectorAll('[data-page]').forEach(element =>
    element.classList.toggle('active', element.dataset.page === page)
  );
  document.querySelector('.sidebar')?.classList.remove('open');
  document.querySelector('#sidebarOverlay')?.classList.remove('show');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function closeSidebar() {
  document.querySelector('.sidebar').classList.remove('open');
  document.querySelector('#sidebarOverlay').classList.remove('show');
}

function toggleTheme() {
  document.body.classList.toggle('dark');
  const isDark = document.body.classList.contains('dark');
  document.querySelector('#themeToggle .material-symbols-rounded').textContent = isDark ? 'light_mode' : 'dark_mode';
  localStorage.setItem('nava-theme', isDark ? 'dark' : 'light');
  showToast(isDark ? 'حالت تاریک فعال شد' : 'حالت روشن فعال شد');
}

async function addProduct(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  try {
    await api('/api/products/', {
      method: 'POST',
      body: JSON.stringify({
        name: data.get('name'),
        category: data.get('category'),
        price: Number(data.get('price')),
        stock: Number(data.get('stock')),
        description: data.get('description')
      })
    });
    form.reset();
    await refreshData();
    showToast('محصول جدید با موفقیت ثبت شد');
    goToPage('products');
  } catch (error) {
    showToast(error.message, 'info');
  }
}

async function reduceStock(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  try {
    const result = await api('/api/stock/', {
      method: 'POST',
      body: JSON.stringify({
        product_id: Number(data.get('productId')),
        amount: Number(data.get('amount')),
        reason: data.get('reason'),
        note: data.get('note')
      })
    });
    await refreshData();
    form.reset();
    showToast(`موجودی «${result.product.name}» به‌روزرسانی شد`);
  } catch (error) {
    showToast(error.message, 'info');
  }
}

async function increaseStock(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  try {
    const result = await api('/api/stock/increase/', {
      method: 'POST',
      body: JSON.stringify({
        product_id: Number(data.get('productId')),
        amount: Number(data.get('amount')),
        reason: data.get('reason'),
        note: data.get('note')
      })
    });
    await refreshData();
    form.reset();
    showToast(`موجودی «${result.product.name}» افزایش یافت`);
  } catch (error) {
    showToast(error.message, 'info');
  }
}

async function deleteProduct(id) {
  try {
    await api(`/api/products/${id}/`, { method: 'DELETE' });
    await refreshData();
    showToast('محصول با موفقیت حذف شد');
  } catch (error) {
    showToast(error.message, 'info');
  }
}

async function saveSetting(field, value, input) {
  try {
    settings = await api('/api/settings/', {
      method: 'PATCH',
      body: JSON.stringify({ [field]: value })
    });
    showToast('تنظیمات ذخیره شد');
  } catch (error) {
    input.checked = !value;
    showToast(error.message, 'info');
  }
}

function bindEvents() {
  document.addEventListener('click', event => {
    const pageTarget = event.target.closest('[data-page]');
    if (pageTarget) goToPage(pageTarget.dataset.page);
    const submenu = event.target.closest('[data-submenu]');
    if (submenu) {
      submenu.classList.toggle('open');
      document.querySelector(`#${submenu.dataset.submenu}`).classList.toggle('open');
    }
    const deleteButton = event.target.closest('.delete-product');
    if (deleteButton) deleteProduct(Number(deleteButton.dataset.id));
  });
  document.querySelector('#menuToggle').addEventListener('click', () => {
    document.querySelector('.sidebar').classList.add('open');
    document.querySelector('#sidebarOverlay').classList.add('show');
  });
  document.querySelector('#sidebarClose').addEventListener('click', closeSidebar);
  document.querySelector('#sidebarOverlay').addEventListener('click', closeSidebar);
  document.querySelector('#productSearch').addEventListener('input', () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(loadProducts, 250);
  });
  document.querySelector('#categoryFilter').addEventListener('change', loadProducts);
  document.querySelector('#themeToggle').addEventListener('click', toggleTheme);
  document.querySelector('#settingsTheme').addEventListener('click', toggleTheme);
  document.querySelector('#addProductForm').addEventListener('submit', addProduct);
  document.querySelector('#stockForm').addEventListener('submit', reduceStock);
  document.querySelector('#increaseStockForm').addEventListener('submit', increaseStock);
  document.querySelector('#notificationsSetting').addEventListener('change', event =>
    saveSetting('notifications_enabled', event.currentTarget.checked, event.currentTarget)
  );
  document.querySelector('#lowStockSetting').addEventListener('change', event =>
    saveSetting('show_low_stock', event.currentTarget.checked, event.currentTarget)
  );
}

async function loadProducts() {
  const query = new URLSearchParams();
  const search = document.querySelector('#productSearch').value.trim();
  const category = document.querySelector('#categoryFilter').value;
  if (search) query.set('search', search);
  if (category !== 'all') query.set('category', category);
  try {
    const result = await api(`/api/products/?${query.toString()}`);
    renderProducts(result.results);
  } catch (error) {
    showToast(error.message, 'info');
  }
}

async function init() {
  if (localStorage.getItem('nava-theme') === 'dark') {
    document.body.classList.add('dark');
    document.querySelector('#themeToggle .material-symbols-rounded').textContent = 'light_mode';
  }
  document.querySelectorAll('#addProductForm input[type="number"]').forEach(input => {
    input.min = input.name === 'price' ? '1' : '0';
  });
  document.querySelector('#topbarDate').textContent = `امروز، ${new Intl.DateTimeFormat('fa-IR', {
    dateStyle: 'full'
  }).format(new Date())}`;
  bindEvents();
  try {
    await refreshData();
  } catch (error) {
    showToast(error.message, 'info');
  }
}

document.addEventListener('DOMContentLoaded', init);
