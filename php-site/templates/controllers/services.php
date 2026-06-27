<?php
$blocks   = blocks_for('services');
$services = db()->query('SELECT * FROM services WHERE is_active = 1 ORDER BY sort ASC')->fetchAll();
render('services', ['blocks' => $blocks, 'services' => $services, 'page_title' => $blocks['title']]);
