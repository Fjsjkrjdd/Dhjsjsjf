<?php
require_once __DIR__ . '/../../includes/yookassa.php';
require_once __DIR__ . '/../../includes/auth.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    redirect(url('booking'));
}

$name  = trim($_POST['name'] ?? '');
$phone = trim($_POST['phone'] ?? '');
$email = trim($_POST['email'] ?? '');
$date  = trim($_POST['preferred_date'] ?? '');
$comment = trim($_POST['comment'] ?? '');
$slug  = trim($_POST['service'] ?? '');
$pay   = !empty($_POST['pay']);
$agree = !empty($_POST['agree']);

if ($name === '' || $phone === '' || !$agree) {
    flash('Пожалуйста, заполните имя, телефон и подтвердите согласие на обработку данных.');
    redirect(url('booking') . ($slug ? '?service=' . urlencode($slug) : ''));
}

$service = null;
if ($slug) {
    $st = db()->prepare('SELECT * FROM services WHERE slug = ?');
    $st->execute([$slug]);
    $service = $st->fetch() ?: null;
}

$st = db()->prepare('INSERT INTO orders (service_id, service_title, customer_name, customer_phone, customer_email, preferred_date, comment, amount, status, created_at)
    VALUES (?,?,?,?,?,?,?,?,?,?)');
$st->execute([
    $service['id'] ?? null,
    $service['title'] ?? 'Консультация',
    $name, $phone, $email, $date, $comment,
    $service['price'] ?? 0,
    'new', now(),
]);
$orderId = (int) db()->lastInsertId();

// Онлайн-оплата через кассу (если включена и услуга платная).
if ($pay && $service && (int) $service['price'] > 0 && payments_configured()) {
    $payment = yk_create_payment(
        (int) $service['price'],
        'Оплата услуги: ' . $service['title'],
        url('booking/success') . '?order=' . $orderId,
        $email, $phone,
        ['order_id' => (string) $orderId]
    );
    if ($payment && !empty($payment['confirmation_url'])) {
        $u = db()->prepare('UPDATE orders SET payment_id=?, payment_status=?, payment_url=?, receipt_status=? WHERE id=?');
        $u->execute([
            $payment['id'], $payment['status'], $payment['confirmation_url'],
            setting('fiscal_enabled') === '1' ? 'pending' : 'none',
            $orderId,
        ]);
        redirect($payment['confirmation_url']);
    }
    flash('Заявка принята, но онлайн-оплату начать не удалось. Я свяжусь с вами для подтверждения.');
    redirect(url('booking/success') . '?order=' . $orderId);
}

redirect(url('booking/success') . '?order=' . $orderId);
