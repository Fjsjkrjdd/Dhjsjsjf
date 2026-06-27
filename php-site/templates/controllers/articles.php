<?php
$blocks   = blocks_for('articles');
$articles = db()->query('SELECT * FROM articles WHERE is_published = 1 ORDER BY published_at DESC')->fetchAll();
render('articles', ['blocks' => $blocks, 'articles' => $articles, 'page_title' => $blocks['title']]);
