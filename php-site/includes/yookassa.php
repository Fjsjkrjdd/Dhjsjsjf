<?php
/** Онлайн-касса ЮKassa: создание платежа, чек (54-ФЗ), запрос статуса. */

require_once __DIR__ . '/functions.php';

function payments_configured(): bool
{
    return setting('payments_enabled') === '1'
        && setting('yookassa_shop_id') !== ''
        && setting('yookassa_secret_key') !== '';
}

function yk_auth_header(): string
{
    return 'Basic ' . base64_encode(setting('yookassa_shop_id') . ':' . setting('yookassa_secret_key'));
}

function yk_receipt(int $amount, string $description, string $email, string $phone): ?array
{
    if (setting('fiscal_enabled') !== '1') {
        return null;
    }
    $customer = [];
    if ($email) {
        $customer['email'] = $email;
    }
    if ($phone) {
        $customer['phone'] = preg_replace('/[^0-9+]/', '', $phone);
    }
    if (!$customer) {
        return null;
    }
    return [
        'customer'        => $customer,
        'tax_system_code' => (int) setting('tax_system_code', '2'),
        'items'           => [[
            'description'    => mb_substr($description, 0, 128),
            'quantity'       => '1.00',
            'amount'         => ['value' => number_format($amount, 2, '.', ''), 'currency' => 'RUB'],
            'vat_code'       => (int) setting('vat_code', '1'),
            'payment_subject'=> setting('payment_subject', 'service'),
            'payment_mode'   => setting('payment_mode', 'full_payment'),
        ]],
    ];
}

/**
 * Создаёт платёж в ЮKassa. Возвращает массив с ключами id, status, confirmation_url
 * или null при ошибке.
 */
function yk_create_payment(int $amount, string $description, string $returnUrl, string $email, string $phone, array $metadata = []): ?array
{
    $body = [
        'amount'       => ['value' => number_format($amount, 2, '.', ''), 'currency' => 'RUB'],
        'capture'      => true,
        'confirmation' => ['type' => 'redirect', 'return_url' => $returnUrl],
        'description'  => mb_substr($description, 0, 128),
        'metadata'     => $metadata,
    ];
    $receipt = yk_receipt($amount, $description, $email, $phone);
    if ($receipt) {
        $body['receipt'] = $receipt;
    }

    $ch = curl_init('https://api.yookassa.ru/v3/payments');
    curl_setopt_array($ch, [
        CURLOPT_POST           => true,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER     => [
            'Content-Type: application/json',
            'Idempotence-Key: ' . bin2hex(random_bytes(12)),
            'Authorization: ' . yk_auth_header(),
        ],
        CURLOPT_POSTFIELDS     => json_encode($body, JSON_UNESCAPED_UNICODE),
        CURLOPT_TIMEOUT        => 30,
    ]);
    $resp = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($code < 200 || $code >= 300 || !$resp) {
        error_log('YooKassa create error ' . $code . ': ' . $resp);
        return null;
    }
    $data = json_decode($resp, true);
    return [
        'id'               => $data['id'] ?? null,
        'status'           => $data['status'] ?? 'pending',
        'confirmation_url' => $data['confirmation']['confirmation_url'] ?? null,
    ];
}

/** Запрашивает текущий статус платежа. */
function yk_get_payment(string $paymentId): ?array
{
    $ch = curl_init('https://api.yookassa.ru/v3/payments/' . urlencode($paymentId));
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER     => ['Authorization: ' . yk_auth_header()],
        CURLOPT_TIMEOUT        => 30,
    ]);
    $resp = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    if ($code < 200 || $code >= 300 || !$resp) {
        return null;
    }
    return json_decode($resp, true);
}
