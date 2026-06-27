<?php
$blocks    = blocks_for('about');
$education = db()->query('SELECT * FROM education ORDER BY sort ASC')->fetchAll();
$diplomas  = db()->query('SELECT * FROM diplomas WHERE is_published = 1 ORDER BY sort ASC')->fetchAll();
render('about', ['blocks' => $blocks, 'education' => $education, 'diplomas' => $diplomas, 'page_title' => $blocks['title']]);
