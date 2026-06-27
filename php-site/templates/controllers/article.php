<?php
/** @var string $article_slug */
$st = db()->prepare('SELECT * FROM articles WHERE slug = ? AND is_published = 1');
$st->execute([$article_slug]);
$article = $st->fetch();
if (!$article) {
    not_found();
}
render('article', [
    'article'          => $article,
    'page_title'       => $article['meta_title'] ?: $article['title'],
    'meta_description' => $article['meta_description'] ?: $article['excerpt'],
]);
