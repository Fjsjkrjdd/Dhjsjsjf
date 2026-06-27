<?php
/** Управление блоками главной страницы. */

if (!function_exists('home_section_types')):

function home_section_types(): array
{
    return [
        'hero'     => 'Обложка (герой)',
        'intro'    => 'О подходе',
        'services' => 'Услуги и цены',
        'methods'  => 'Методы работы',
        'diplomas' => 'Дипломы',
        'steps'    => 'Этапы работы',
        'reviews'  => 'Отзывы',
        'cta'      => 'Призыв к действию',
        'custom'   => 'Произвольный блок (HTML)',
    ];
}

function home_sections_seed_defaults(PDO $pdo): void
{
    $defaults = [
        ['hero', 'Обложка', 0],
        ['intro', 'О подходе', 1],
        ['services', 'Услуги', 2],
        ['methods', 'Методы', 3],
        ['diplomas', 'Дипломы', 4],
        ['steps', 'Этапы', 5],
        ['reviews', 'Отзывы', 6],
        ['cta', 'Призыв', 7],
    ];
    $st = $pdo->prepare('INSERT INTO home_sections (section_type, title, sort, is_active) VALUES (?, ?, ?, 1)');
    foreach ($defaults as $d) {
        $st->execute($d);
    }
}

function home_sections_all(bool $activeOnly = false): array
{
    $sql = 'SELECT * FROM home_sections';
    if ($activeOnly) {
        $sql .= ' WHERE is_active = 1';
    }
    $sql .= ' ORDER BY sort ASC, id ASC';
    return db()->query($sql)->fetchAll();
}

endif;
