document.addEventListener('DOMContentLoaded', () => {
  document.body.innerHTML = document.body.innerHTML.replaceAll('ر.س', 'د.ع');
  const paymentSelect = document.querySelector('select[name="payment_method"]');
  if (paymentSelect) {
    const deferredOption = document.createElement('option');
    deferredOption.value = 'آجل';
    deferredOption.textContent = 'آجل / دين';
    paymentSelect.appendChild(deferredOption);
    const customerField = document.createElement('label');
    customerField.className = 'credit-customer-field';
    customerField.style.cssText = 'flex:1;min-width:150px;color:#697779;font-size:10px;font-weight:700';
    customerField.innerHTML = 'اسم الزبون (اختياري)<input name="customer_name" placeholder="اسم الزبون" style="display:block;width:100%;height:38px;margin-top:6px;border:1px solid #e6ecec;border-radius:7px;padding:0 10px;font-size:10px;outline:0">';
    customerField.hidden = false;
    paymentSelect.closest('.checkout-bar').insertBefore(customerField, paymentSelect.closest('label').nextSibling);
    paymentSelect.addEventListener('change', () => {
      customerField.querySelector('input').placeholder = paymentSelect.value === 'آجل' ? 'اسم الزبون المدين' : 'اسم الزبون';
      customerField.firstChild.textContent = paymentSelect.value === 'آجل' ? 'اسم الزبون المدين' : 'اسم الزبون (اختياري)';
      customerField.querySelector('input').required = paymentSelect.value === 'آجل';
    });
  }
  document.querySelectorAll('.show-code').forEach((button) => button.addEventListener('click', () => {
    const input = button.parentElement.querySelector('input');
    input.type = input.type === 'password' ? 'text' : 'password';
    button.textContent = input.type === 'password' ? '◉' : '◌';
  }));
  const sidebar = document.querySelector('.sidebar');
  const menu = document.querySelector('.mobile-menu');
  if (menu) menu.addEventListener('click', () => sidebar.classList.toggle('open'));
  document.querySelectorAll('[data-modal-open]').forEach((button) => {
    button.addEventListener('click', () => document.getElementById(button.dataset.modalOpen).classList.add('open'));
  });
  document.querySelectorAll('.modal-close').forEach((button) => {
    button.addEventListener('click', () => button.closest('.modal').classList.remove('open'));
  });
  document.querySelectorAll('.modal').forEach((modal) => modal.addEventListener('click', (event) => {
    if (event.target === modal) modal.classList.remove('open');
  }));

  const cart = new Map();
  const cartItems = document.getElementById('cart-items');
  const totalElement = document.getElementById('cart-total');
  if (!cartItems || !totalElement) return;
  const formatMoney = (value) => `${value.toLocaleString('ar-IQ', { minimumFractionDigits: 2 })} د.ع`;
  const renderCart = () => {
    if (!cart.size) {
      cartItems.innerHTML = '<div class="cart-empty">السلة فارغة <span>← اختر صنفًا للبدء</span></div>';
      totalElement.textContent = '0.00 د.ع';
      return;
    }
    let total = 0;
    cartItems.innerHTML = [...cart.values()].map((item) => {
      total += item.price * item.quantity;
      return `<div class="cart-line"><input type="hidden" name="product_id" value="${item.id}"><input type="hidden" name="quantity" value="${item.quantity}"><span class="line-name">${item.name}</span><div class="qty"><button type="button" data-minus="${item.id}">−</button><span>${item.quantity}</span><button type="button" data-plus="${item.id}">＋</button></div><b class="line-price">${formatMoney(item.price * item.quantity)}</b><button type="button" class="remove-line" data-remove="${item.id}">×</button></div>`;
    }).join('');
    totalElement.textContent = formatMoney(total);
  };
  document.querySelectorAll('.product-tile').forEach((tile) => tile.addEventListener('click', () => {
    const id = tile.dataset.id;
    const item = cart.get(id) || { id, name: tile.dataset.name, price: Number(tile.dataset.price), stock: Number(tile.dataset.stock), quantity: 0 };
    if (item.quantity < item.stock) item.quantity += 1;
    cart.set(id, item); renderCart();
  }));
  cartItems.addEventListener('click', (event) => {
    const button = event.target.closest('button'); if (!button) return;
    const id = button.dataset.plus || button.dataset.minus || button.dataset.remove; const item = cart.get(id);
    if (button.dataset.plus && item.quantity < item.stock) item.quantity += 1;
    if (button.dataset.minus) item.quantity -= 1;
    if (button.dataset.remove || item.quantity <= 0) cart.delete(id);
    renderCart();
  });
});