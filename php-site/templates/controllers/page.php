<?php
/** @var array $page */
render('page', [
    'page'             => $page,
    'page_title'       => $page['meta_title'] ?: $page['title'],
    'meta_description' => $page['meta_description'],
]);
