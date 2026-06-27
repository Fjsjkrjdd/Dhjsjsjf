<?php
/** @var array $blocks $services $diplomas $reviews $sections */
require_once __DIR__ . '/../includes/yookassa.php';

foreach ($sections as $section) {
    require __DIR__ . '/partials/home_section.php';
}
