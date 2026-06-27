<?php /** @var array $r */ ?>
<figure class="card review-card">
    <div class="stars">
        <?php for ($i = 0; $i < 5; $i++): ?>
            <span class="star <?= $i < (int) $r['rating'] ? 'on' : '' ?>">★</span>
        <?php endfor; ?>
    </div>
    <blockquote><?= e($r['body']) ?></blockquote>
    <figcaption>
        <span class="review-author"><?= e($r['author']) ?></span>
        <?php if ($r['source']): ?><span class="review-source">· <?= e($r['source']) ?></span><?php endif; ?>
    </figcaption>
</figure>
