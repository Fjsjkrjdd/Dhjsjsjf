<?php /** @var array $article */ ?>
<article class="section">
    <div class="container narrow">
        <a href="<?= e(url('articles')) ?>" class="link-arrow">← Все статьи</a>
        <?php if ($article['category']): ?><span class="article-cat" style="margin-top:1rem;display:inline-block"><?= e($article['category']) ?></span><?php endif; ?>
        <h1><?= e($article['title']) ?></h1>
        <p class="muted"><?= e(format_date_ru($article['published_at'] ?: 'now')) ?></p>
        <?php if ($article['cover']): ?>
            <div class="article-hero"><img src="<?= e(asset($article['cover'])) ?>" alt="<?= e($article['title']) ?>"></div>
        <?php endif; ?>
        <div class="prose"><?= $article['body'] ?></div>
    </div>
</article>
