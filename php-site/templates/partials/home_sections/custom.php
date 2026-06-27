<?php /** @var array $section */ ?>
<section class="section">
    <div class="container narrow">
        <?php if ($section['title']): ?><h2 class="section-center"><?= e($section['title']) ?></h2><?php endif; ?>
        <?php if ($section['subtitle']): ?><p class="lead section-center"><?= e($section['subtitle']) ?></p><?php endif; ?>
        <?php if ($section['body']): ?><div class="prose"><?= $section['body'] ?></div><?php endif; ?>
    </div>
</section>
