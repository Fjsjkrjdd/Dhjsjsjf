<?php
$blocks  = blocks_for('reviews');
$reviews = db()->query('SELECT * FROM reviews WHERE is_published = 1 ORDER BY sort ASC')->fetchAll();
render('reviews', ['blocks' => $blocks, 'reviews' => $reviews, 'page_title' => $blocks['title']]);
