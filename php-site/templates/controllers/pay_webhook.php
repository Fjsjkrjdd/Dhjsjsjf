<?php
/** Приём уведомлений ЮKassa: {BASE_URL}/pay/webhook */
require_once __DIR__ . '/../../includes/functions.php';

$raw  = file_get_contents('php://input');
$data = json_decode($raw, true);
$obj  = $data['object'] ?? null;
header('Content-Type: application/json');

if (!$obj || empty($obj['id'])) {
    echo json_encode(['ok' => true]);
    exit;
}

$orderId = (int) ($obj['metadata']['order_id'] ?? 0);
$st = db()->prepare('SELECT * FROM orders WHERE payment_id = ? OR id = ? LIMIT 1');
$st->execute([$obj['id'], $orderId]);
$order = $st->fetch();
if (!$order) {
    echo json_encode(['ok' => true]);
    exit;
}

$event     = $data['event'] ?? '';
$succeeded = $event === 'payment.succeeded' || ($obj['status'] ?? '') === 'succeeded';
$canceled  = $event === 'payment.canceled' || ($obj['status'] ?? '') === 'canceled';

$u = db()->prepare('UPDATE orders SET payment_id=?, payment_status=?, status=?, receipt_status=? WHERE id=?');
$u->execute([
    $obj['id'],
    $obj['status'] ?? $order['payment_status'],
    $succeeded ? 'paid' : ($canceled ? 'cancelled' : $order['status']),
    ($succeeded && $order['receipt_status'] === 'pending') ? 'registered' : $order['receipt_status'],
    $order['id'],
]);

echo json_encode(['ok' => true]);
