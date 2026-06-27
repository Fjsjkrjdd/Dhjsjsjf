<?php
require_once __DIR__ . '/../../includes/yookassa.php';
$blocks   = blocks_for('booking');
$services = db()->query('SELECT * FROM services WHERE is_active = 1 AND is_bookable = 1 ORDER BY sort ASC')->fetchAll();
$selected = $_GET['service'] ?? '';
render('booking', [
    'blocks'           => $blocks,
    'services'         => $services,
    'selected'         => $selected,
    'payments_enabled' => payments_configured(),
    'page_title'       => $blocks['title'],
]);
