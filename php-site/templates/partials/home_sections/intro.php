<?php /** @var array $blocks $section */ ?>
<section class="section section-center narrow">
    <div class="container">
        <h2><?= e($section['title'] ?: $blocks['intro_title']) ?></h2>
        <p class="lead"><?= e($section['body'] ?: $blocks['intro_text']) ?></p>
    </div>
</section>
