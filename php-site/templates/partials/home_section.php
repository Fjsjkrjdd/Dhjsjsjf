<?php
/** Рендер одного блока главной страницы. @var array $section $blocks $services $diplomas $reviews */
$type = $section['section_type'];
$partial = __DIR__ . '/home_sections/' . $type . '.php';
if (is_file($partial)) {
    require $partial;
}
