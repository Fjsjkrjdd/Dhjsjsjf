<?php /** @var array $blocks $diplomas $section */ ?>
<section class="section section-alt">
    <div class="container">
        <div class="section-head">
            <h2><?= e($section['title'] ?: $blocks['diplomas_title']) ?></h2>
            <p><?= e($section['subtitle'] ?: $blocks['diplomas_subtitle']) ?></p>
        </div>
        <?php require __DIR__ . '/../diploma_gallery.php'; ?>
    </div>
</section>
