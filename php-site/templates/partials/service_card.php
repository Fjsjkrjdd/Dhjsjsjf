<?php /** @var array $s */ ?>
<div class="card service-card">
    <div class="service-ic"><?= service_icon($s['icon']) ?></div>
    <h3><?= e($s['title']) ?></h3>
    <p class="card-text"><?= e($s['short_description']) ?></p>
    <div class="service-foot">
        <div>
            <span class="price"><?= format_price((int) $s['price']) ?> ₽</span>
            <?php if (!empty($s['old_price'])): ?><span class="old-price"><?= format_price((int) $s['old_price']) ?> ₽</span><?php endif; ?>
            <?php if ($s['duration']): ?><span class="duration"><?= e($s['duration']) ?></span><?php endif; ?>
        </div>
        <a href="<?= e(url('booking') . '?service=' . urlencode($s['slug'])) ?>" class="btn btn-primary btn-sm">Записаться</a>
    </div>
</div>
