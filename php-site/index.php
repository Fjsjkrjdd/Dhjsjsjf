<?php
/** Главный контроллер публичного сайта (ЧПУ через .htaccess). */

require_once __DIR__ . '/includes/functions.php';
require_once __DIR__ . '/includes/auth.php';

$cfg = app_config();
if (!empty($cfg['timezone'])) {
    date_default_timezone_set($cfg['timezone']);
}

/** Рендер публичной страницы внутри общего макета. */
function render(string $template, array $vars = []): void
{
    extract($vars, EXTR_SKIP);
    ob_start();
    require __DIR__ . '/templates/' . $template . '.php';
    $content = ob_get_clean();
    require __DIR__ . '/templates/layout.php';
}

function not_found(): void
{
    http_response_code(404);
    render('not_found', ['page_title' => 'Страница не найдена']);
    exit;
}

$route = trim($_GET['route'] ?? '', '/');
$parts = $route === '' ? [] : explode('/', $route);
$seg0  = $parts[0] ?? '';

switch ($seg0) {
    case '':
        require __DIR__ . '/templates/controllers/home.php';
        break;

    case 'services':
        require __DIR__ . '/templates/controllers/services.php';
        break;

    case 'about':
        require __DIR__ . '/templates/controllers/about.php';
        break;

    case 'reviews':
        require __DIR__ . '/templates/controllers/reviews.php';
        break;

    case 'articles':
        if (isset($parts[1]) && $parts[1] !== '') {
            $article_slug = $parts[1];
            require __DIR__ . '/templates/controllers/article.php';
        } else {
            require __DIR__ . '/templates/controllers/articles.php';
        }
        break;

    case 'contacts':
        require __DIR__ . '/templates/controllers/contacts.php';
        break;

    case 'booking':
        if (($parts[1] ?? '') === 'submit') {
            require __DIR__ . '/templates/controllers/booking_submit.php';
        } elseif (($parts[1] ?? '') === 'success') {
            require __DIR__ . '/templates/controllers/booking_success.php';
        } else {
            require __DIR__ . '/templates/controllers/booking.php';
        }
        break;

    case 'pay':
        if (($parts[1] ?? '') === 'webhook') {
            require __DIR__ . '/templates/controllers/pay_webhook.php';
        } else {
            not_found();
        }
        break;

    default:
        // Произвольная страница по slug.
        $st = db()->prepare('SELECT * FROM pages WHERE slug = ? AND is_published = 1');
        $st->execute([$seg0]);
        $page = $st->fetch();
        if ($page) {
            require __DIR__ . '/templates/controllers/page.php';
        } else {
            not_found();
        }
}
