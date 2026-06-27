<?php
require_once __DIR__ . '/../../includes/yookassa.php';

$orderId = (int) ($_GET['order'] ?? 0);
$paid    = false;
if ($orderId) {
    $st = db()->prepare('SELECT * FROM orders WHERE id = ?');
    $st->execute([$orderId]);
    $order = $st->fetch();
    if ($order && $order['payment_id'] && payments_configured()) {
        $p = yk_get_payment($order['payment_id']);
        if ($p) {
            $paid = ($p['status'] ?? '') === 'succeeded' || !empty($p['paid']);
            $u = db()->prepare('UPDATE orders SET payment_status=?, status=?, receipt_status=? WHERE id=?');
            $u->execute([
                $p['status'] ?? $order['payment_status'],
                $paid ? 'paid' : $order['status'],
                ($paid && $order['receipt_status'] === 'pending') ? 'registered' : $order['receipt_status'],
                $orderId,
            ]);
        }
    }
}
render('booking_success', ['paid' => $paid, 'page_title' => 'Спасибо за заявку']);
