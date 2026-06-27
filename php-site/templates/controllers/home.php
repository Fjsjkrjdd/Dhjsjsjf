<?php
$blocks   = blocks_for('home');
$services = db()->query('SELECT * FROM services WHERE is_active = 1 ORDER BY sort ASC')->fetchAll();
$diplomas = db()->query('SELECT * FROM diplomas WHERE is_published = 1 ORDER BY sort ASC')->fetchAll();
$reviews  = db()->query('SELECT * FROM reviews WHERE is_published = 1 ORDER BY sort ASC LIMIT 6')->fetchAll();

render('home', [
    'blocks'   => $blocks,
    'services' => $services,
    'diplomas' => $diplomas,
    'reviews'  => $reviews,
]);
