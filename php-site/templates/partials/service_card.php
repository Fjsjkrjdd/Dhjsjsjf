<?php /** @var array $s */ ?>
<div class="card service-card">
    <div class="service-ic"><?= service_icon($s['icon']) ?></div>
    <h3><?= e($s['title']) ?></h3>
    <p class="card-text"><?= e($s['short_description']) ?></p>
    <div class="service-foot">
        <?php require __DIR__ . '/price_block.php'; ?>
        <?php if ($s['is_bookable']): ?>
            <div class="service-actions">
                <a href="<?= e(url('booking') . '?service=' . urlencode($s['slug'])) ?>" class="btn btn-primary btn-sm">Записаться</a>
                <?php if (payments_accepted() && (int) $s['price'] > 0): ?>
                    <a href="<?= e(url('booking') . '?service=' . urlencode($s['slug']) . '&pay=1') ?>" class="btn btn-outline btn-sm">Оплатить</a>
                <?php endif; ?>
            </div>
        <?php endif; ?>
    </div>
</div>
