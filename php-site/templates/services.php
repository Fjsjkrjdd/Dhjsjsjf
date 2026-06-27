<?php /** @var array $blocks $services */ ?>
<section class="section">
    <div class="container narrow-wide">
        <h1><?= e($blocks['title']) ?></h1>
        <p class="lead"><?= e($blocks['subtitle']) ?></p>

        <div class="service-rows">
            <?php foreach ($services as $s):
                $gallery = service_gallery($s);
            ?>
            <article class="service-row card">
                <?php if ($gallery): ?>
                    <div class="service-row-photo">
                        <img src="<?= e(asset($gallery[0])) ?>" alt="<?= e($s['title']) ?>">
                    </div>
                <?php else: ?>
                    <div class="service-ic big"><?= service_icon($s['icon']) ?></div>
                <?php endif; ?>
                <div class="service-row-body">
                    <h2><?= e($s['title']) ?></h2>
                    <p><?= e($s['description'] ?: $s['short_description']) ?></p>
                    <?php if ($s['duration']): ?><span class="duration-pill"><?= e($s['duration']) ?></span><?php endif; ?>
                    <?php if (count($gallery) > 1): ?>
                        <div class="service-gallery-mini">
                            <?php foreach (array_slice($gallery, 1) as $img): ?>
                                <img src="<?= e(asset($img)) ?>" alt="" loading="lazy">
                            <?php endforeach; ?>
                        </div>
                    <?php endif; ?>
                </div>
                <div class="service-row-price">
                    <?php require __DIR__ . '/partials/price_block.php'; ?>
                    <?php if ($s['is_bookable']): ?>
                        <div class="service-row-actions">
                            <a href="<?= e(url('booking') . '?service=' . urlencode($s['slug'])) ?>" class="btn btn-primary btn-sm">Записаться</a>
                            <?php if (payments_accepted() && (int) $s['price'] > 0): ?>
                                <a href="<?= e(url('booking') . '?service=' . urlencode($s['slug']) . '&pay=1') ?>" class="btn btn-outline btn-sm">Оплатить онлайн</a>
                            <?php endif; ?>
                        </div>
                    <?php endif; ?>
                </div>
            </article>
            <?php endforeach; ?>
        </div>

        <p class="note-box"><?= e($blocks['note']) ?></p>
    </div>
</section>
