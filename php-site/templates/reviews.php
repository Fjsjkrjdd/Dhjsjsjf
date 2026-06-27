<?php /** @var array $blocks $reviews */ ?>
<section class="section">
    <div class="container">
        <h1><?= e($blocks['title']) ?></h1>
        <p class="lead"><?= e($blocks['subtitle']) ?></p>

        <?php $widget = setting('yandex_reviews_widget'); ?>
        <?php if ($widget): ?>
            <div class="yandex-widget"><?= $widget ?></div>
        <?php endif; ?>

        <?php if ($reviews): ?>
            <div class="cards-grid" style="margin-top:2rem">
                <?php foreach ($reviews as $r): ?>
                    <?php require __DIR__ . '/partials/review_card.php'; ?>
                <?php endforeach; ?>
            </div>
        <?php elseif (!$widget): ?>
            <p class="empty-note">Отзывы пока не добавлены.</p>
        <?php endif; ?>

        <?php if (setting('yandex_maps')): ?>
            <div class="section-center" style="margin-top:2rem">
                <a href="<?= e(setting('yandex_maps')) ?>" target="_blank" rel="noopener" class="btn btn-outline">Смотреть отзывы на Яндекс Картах</a>
            </div>
        <?php endif; ?>
    </div>
</section>
