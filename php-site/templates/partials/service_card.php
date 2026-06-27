<?php /** @var array $s */ ?>
<div class="card service-card">
    <?php $gallery = service_gallery($s); ?>
    <?php if ($gallery): ?>
        <div class="service-ic service-ic-photo">
            <img src="<?= e(asset($gallery[0])) ?>" alt="<?= e($s['title']) ?>">
        </div>
    <?php else: ?>
        <div class="service-ic"><?= service_icon($s['icon']) ?></div>
    <?php endif; ?>
    <h3><?= e($s['title']) ?></h3>
    <p class="card-text"><?= e($s['short_description']) ?></p>
    <?php if (count($gallery) > 1): ?>
        <div class="service-gallery-mini">
            <?php foreach (array_slice($gallery, 1, 3) as $img): ?>
                <img src="<?= e(asset($img)) ?>" alt="" loading="lazy">
            <?php endforeach; ?>
        </div>
    <?php endif; ?>
    <div class="service-foot">
        <div>
            <span class="price"><?= format_price((int) $s['price']) ?> ₽</span>
            <?php if (!empty($s['old_price'])): ?><span class="old-price"><?= format_price((int) $s['old_price']) ?> ₽</span><?php endif; ?>
            <?php if ($s['duration']): ?><span class="duration"><?= e($s['duration']) ?></span><?php endif; ?>
        </div>
        <div class="service-actions">
            <?php if ($s['is_bookable']): ?>
                <a href="<?= e(url('booking') . '?service=' . urlencode($s['slug'])) ?>" class="btn btn-primary btn-sm">Записаться</a>
                <?php if (payments_accepted() && (int) $s['price'] > 0): ?>
                    <a href="<?= e(url('booking') . '?service=' . urlencode($s['slug']) . '&pay=1') ?>" class="btn btn-outline btn-sm">Оплатить</a>
                <?php endif; ?>
            <?php endif; ?>
        </div>
    </div>
</div>
