<?php /** @var array $items */
$statuses = ['new'=>'Новая','confirmed'=>'Подтверждена','paid'=>'Оплачена','cancelled'=>'Отменена','completed'=>'Завершена'];
$pay = ['pending'=>'Ожидает','waiting_for_capture'=>'Холдирование','succeeded'=>'Оплачено','canceled'=>'Отменено'];
?>
<div class="admin-head"><div><h1>Заявки и оплаты</h1><p>Заявки с сайта и статусы онлайн-оплат.</p></div></div>

<?php foreach ($items as $o): ?>
    <div class="adm-card">
        <div class="adm-row">
            <div>
                <strong><?= e($o['customer_name']) ?></strong> · <?= e($o['customer_phone']) ?>
                <?php if ($o['customer_email']): ?> · <?= e($o['customer_email']) ?><?php endif; ?>
                <div class="muted" style="font-size:.88rem;margin-top:.2rem">
                    <?= e($o['service_title']) ?><?= $o['amount'] ? ' · ' . format_price((int) $o['amount']) . ' ₽' : '' ?><?= $o['preferred_date'] ? ' · ' . e($o['preferred_date']) : '' ?>
                </div>
                <?php if ($o['comment']): ?><div class="muted" style="font-size:.88rem">«<?= e($o['comment']) ?>»</div><?php endif; ?>
                <div class="muted" style="font-size:.78rem;margin-top:.2rem"><?= e($o['created_at']) ?>
                    <?php if ($o['payment_id']): ?> · Оплата: <?= e($pay[$o['payment_status']] ?? $o['payment_status']) ?><?php if ($o['receipt_status'] !== 'none'): ?> · чек: <?= e($o['receipt_status']) ?><?php endif; ?><?php endif; ?>
                </div>
            </div>
            <form method="post" action="<?= e(admin_url('orders')) ?>" class="adm-actions">
                <?= csrf_field() ?><input type="hidden" name="id" value="<?= (int) $o['id'] ?>">
                <select name="status" style="padding:7px 10px;border:1px solid var(--cream-deep);border-radius:8px">
                    <?php foreach ($statuses as $k => $v): ?><option value="<?= $k ?>" <?= $o['status'] === $k ? 'selected' : '' ?>><?= e($v) ?></option><?php endforeach; ?>
                </select>
                <button class="btn btn-primary btn-sm">ОК</button>
                <button class="btn-danger" name="action" value="delete" onclick="return confirm('Удалить заявку?')">Удалить</button>
            </form>
        </div>
    </div>
<?php endforeach; ?>
<?php if (!$items): ?><div class="adm-card">Заявок пока нет.</div><?php endif; ?>
