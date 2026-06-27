<?php /** @var array $blocks $reviews $section */
$widget = setting('yandex_reviews_widget');
if (!$widget && !$reviews) {
    return;
}
?>
<section class="section section-alt">
    <div class="container">
        <h2 class="section-center"><?= e($section['title'] ?: $blocks['reviews_title']) ?></h2>
        <?php if ($widget): ?>
            <div class="yandex-widget"><?= $widget ?></div>
        <?php else: ?>
            <div class="cards-grid">
                <?php foreach ($reviews as $r): ?>
                    <?php require __DIR__ . '/../review_card.php'; ?>
                <?php endforeach; ?>
            </div>
            <div class="section-center" style="margin-top:2rem">
                <a href="<?= e(url('reviews')) ?>" class="link-arrow">Все отзывы →</a>
            </div>
        <?php endif; ?>
    </div>
</section>
