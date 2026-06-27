<?php /** @var array $blocks $services */ ?>
<section class="section">
    <div class="container narrow-wide">
        <h1><?= e($blocks['title']) ?></h1>
        <p class="lead"><?= e($blocks['subtitle']) ?></p>

        <div class="service-rows">
            <?php foreach ($services as $s): ?>
            <article class="service-row card">
                <div class="service-ic big"><?= service_icon($s['icon']) ?></div>
                <div class="service-row-body">
                    <h2><?= e($s['title']) ?></h2>
                    <p><?= e($s['description'] ?: $s['short_description']) ?></p>
                    <?php if ($s['duration']): ?><span class="duration-pill"><?= e($s['duration']) ?></span><?php endif; ?>
                </div>
                <div class="service-row-price">
                    <div class="price-row">
                        <span class="price"><?= format_price((int) $s['price']) ?> ₽</span>
                        <?php if (!empty($s['old_price'])): ?><span class="old-price"><?= format_price((int) $s['old_price']) ?> ₽</span><?php endif; ?>
                    </div>
                    <?php if ($s['is_bookable']): ?>
                        <a href="<?= e(url('booking') . '?service=' . urlencode($s['slug'])) ?>" class="btn btn-primary btn-sm">Записаться</a>
                    <?php endif; ?>
                </div>
            </article>
            <?php endforeach; ?>
        </div>

        <p class="note-box"><?= e($blocks['note']) ?></p>
    </div>
</section>
