<?php /** @var array $blocks $articles */ ?>
<section class="section">
    <div class="container">
        <h1><?= e($blocks['title']) ?></h1>
        <p class="lead"><?= e($blocks['subtitle']) ?></p>

        <?php if (empty($articles)): ?>
            <p class="empty-note">Статьи пока не опубликованы.</p>
        <?php else: ?>
            <div class="articles-grid">
                <?php foreach ($articles as $a): ?>
                    <a class="card article-card" href="<?= e(url('articles/' . $a['slug'])) ?>">
                        <div class="article-cover">
                            <?php if ($a['cover']): ?>
                                <img src="<?= e(asset($a['cover'])) ?>" alt="<?= e($a['title']) ?>" loading="lazy">
                            <?php else: ?>
                                <span class="cover-stub">Статья</span>
                            <?php endif; ?>
                        </div>
                        <div class="article-body">
                            <?php if ($a['category']): ?><span class="article-cat"><?= e($a['category']) ?></span><?php endif; ?>
                            <h2><?= e($a['title']) ?></h2>
                            <p><?= e($a['excerpt']) ?></p>
                            <span class="article-date"><?= e(format_date_ru($a['published_at'] ?: 'now')) ?></span>
                        </div>
                    </a>
                <?php endforeach; ?>
            </div>
        <?php endif; ?>
    </div>
</section>
