<?php
/** Контроллер админ-панели. Навигация через ?p=... */

require_once __DIR__ . '/../includes/functions.php';
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/yookassa.php';
require_once __DIR__ . '/../includes/blocks.php';
require_once __DIR__ . '/../includes/home_sections.php';

auth_boot();

function render_admin(string $view, array $vars = []): void
{
    $user = current_user();
    extract($vars, EXTR_SKIP);
    ob_start();
    require __DIR__ . '/views/' . $view . '.php';
    $content = ob_get_clean();
    require __DIR__ . '/layout.php';
}

function pv(string $key, $default = ''): string
{
    return trim((string) ($_POST[$key] ?? $default));
}
function pint(string $key, int $default = 0): int
{
    return (int) ($_POST[$key] ?? $default);
}
function pb(string $key): int
{
    return !empty($_POST[$key]) ? 1 : 0;
}

$p      = $_GET['p'] ?? 'dashboard';
$isPost = $_SERVER['REQUEST_METHOD'] === 'POST';

/* ----------------------------- Login/Logout --------------------------- */
if ($p === 'login') {
    if (current_user()) {
        redirect(admin_url());
    }
    $error = '';
    if ($isPost) {
        csrf_check();
        if (attempt_login(pv('email'), pv('password'))) {
            redirect(admin_url());
        }
        $error = 'Неверный e-mail или пароль.';
    }
    require __DIR__ . '/views/login.php';
    exit;
}
if ($p === 'logout') {
    logout();
    redirect(admin_url('login'));
}

$user = require_login();

/* ------------------------------ Actions ------------------------------- */
if ($isPost) {
    csrf_check();
    $pdo = db();

    switch ($p) {
        case 'settings':
            $keys = ['site_name','owner_name','profession','tagline','logo_text','phone','email','address','city','working_hours','map_embed','vk','telegram','whatsapp','instagram','youtube','max','yandex_maps','yandex_reviews_widget','meta_title','meta_description','yookassa_shop_id','tax_system_code','vat_code','payment_subject','payment_mode','color_cream','color_cream_deep','color_sage','color_sage_dark','color_sage_light','color_terracotta','color_terracotta_dark','color_ink','color_ink_soft'];
            foreach ($keys as $k) {
                set_setting($k, pv($k));
            }
            set_setting('payments_enabled', pb('payments_enabled'));
            set_setting('fiscal_enabled', pb('fiscal_enabled'));
            $secret = pv('yookassa_secret_key');
            if ($secret !== '') {
                set_setting('yookassa_secret_key', $secret);
            }
            foreach (['hero_photo' => 'hero_photo_file', 'about_photo' => 'about_photo_file'] as $sk => $field) {
                $uploaded = upload_images($field);
                if (!$uploaded) {
                    $one = upload_image($field);
                    if ($one) {
                        $uploaded = [$one];
                    }
                }
                if ($uploaded) {
                    set_setting($sk, $uploaded[0]);
                } elseif (pv($sk) !== '') {
                    set_setting($sk, pv($sk));
                }
            }
            flash('Настройки сохранены.');
            redirect(admin_url('settings'));

        case 'content':
            $page = pv('page', 'home');
            foreach ($_POST['block'] ?? [] as $id => $val) {
                $st = $pdo->prepare('UPDATE content_blocks SET bvalue = ? WHERE id = ?');
                $st->execute([trim((string) $val), (int) $id]);
            }
            flash('Тексты сохранены.');
            redirect(admin_url('content', ['page' => $page]));

        case 'services':
            $action = pv('action');
            if ($action === 'delete') {
                $pdo->prepare('DELETE FROM services WHERE id = ?')->execute([pint('id')]);
                flash('Услуга удалена.');
                redirect(admin_url('services'));
            }
            $id    = pint('id');
            $title = pv('title');
            $slug  = pv('slug') ?: slugify($title);
            $gallery = [];
            if ($id) {
                $st = $pdo->prepare('SELECT image, gallery FROM services WHERE id = ?');
                $st->execute([$id]);
                $row = $st->fetch();
                if ($row) {
                    $gallery = service_gallery($row);
                }
            }
            if (pb('clear_images')) {
                $gallery = [];
            } else {
                $remove = $_POST['remove_images'] ?? [];
                if (is_array($remove) && $remove) {
                    $gallery = array_values(array_filter($gallery, function ($img) use ($remove) {
                        return !in_array($img, $remove, true);
                    }));
                }
            }
            $newImages = upload_images('image_files');
            $one = upload_image('image_file');
            if ($one) {
                array_unshift($newImages, $one);
            }
            if ($newImages) {
                $gallery = array_merge($gallery, $newImages);
            }
            $gallery = array_values(array_unique(array_filter($gallery)));
            $image = $gallery ? $gallery[0] : '';
            $extra = count($gallery) > 1 ? array_slice($gallery, 1) : [];
            $galleryJson = $extra ? json_encode($extra, JSON_UNESCAPED_UNICODE) : null;
            $data  = [$slug, $title, pv('short_description'), pv('description'), pint('price'),
                pv('old_price') !== '' ? pint('old_price') : null, pv('duration'), pv('icon', 'heart'),
                $image, $galleryJson, pb('is_active'), pb('is_bookable'), pint('sort')];
            if ($id) {
                $sql = 'UPDATE services SET slug=?,title=?,short_description=?,description=?,price=?,old_price=?,duration=?,icon=?,image=?,gallery=?,is_active=?,is_bookable=?,sort=? WHERE id=?';
                $data[] = $id;
                $pdo->prepare($sql)->execute($data);
            } else {
                $pdo->prepare('INSERT INTO services (slug,title,short_description,description,price,old_price,duration,icon,image,gallery,is_active,is_bookable,sort) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)')->execute($data);
            }
            flash('Услуга сохранена.');
            redirect(admin_url('services'));

        case 'diplomas':
            $action = pv('action');
            if ($action === 'delete') {
                $pdo->prepare('DELETE FROM diplomas WHERE id = ?')->execute([pint('id')]);
                flash('Диплом удалён.');
                redirect(admin_url('diplomas'));
            }
            $image = upload_image('image_file') ?: pv('image');
            $images = upload_images('image_files');
            if ($image && !in_array($image, $images, true)) {
                array_unshift($images, $image);
            }
            if (!$images) {
                flash('Выберите одно или несколько изображений для загрузки.');
                redirect(admin_url('diplomas'));
            }
            $sortBase = pint('sort');
            $st = $pdo->prepare('INSERT INTO diplomas (title,description,image,sort,is_published) VALUES (?,?,?,?,1)');
            foreach ($images as $i => $img) {
                $st->execute([pv('title', 'Диплом'), pv('description'), $img, $sortBase + $i]);
            }
            flash(count($images) > 1 ? 'Загружено изображений: ' . count($images) : 'Диплом добавлен.');
            redirect(admin_url('diplomas'));

        case 'education':
            $action = pv('action');
            if ($action === 'delete') {
                $pdo->prepare('DELETE FROM education WHERE id = ?')->execute([pint('id')]);
                flash('Запись удалена.');
                redirect(admin_url('education'));
            }
            $id = pint('id');
            $data = [pv('title'), pv('institution'), pv('year'), pv('description'), pint('sort')];
            if ($id) {
                $data[] = $id;
                $pdo->prepare('UPDATE education SET title=?,institution=?,year=?,description=?,sort=? WHERE id=?')->execute($data);
            } else {
                $pdo->prepare('INSERT INTO education (title,institution,year,description,sort) VALUES (?,?,?,?,?)')->execute($data);
            }
            flash('Сохранено.');
            redirect(admin_url('education'));

        case 'reviews':
            $action = pv('action');
            if ($action === 'delete') {
                $pdo->prepare('DELETE FROM reviews WHERE id = ?')->execute([pint('id')]);
                flash('Отзыв удалён.');
                redirect(admin_url('reviews'));
            }
            $id = pint('id');
            $data = [pv('author'), pv('body'), max(1, min(5, pint('rating', 5))), pv('source'), pv('rdate'), pb('is_published'), pint('sort')];
            if ($id) {
                $data[] = $id;
                $pdo->prepare('UPDATE reviews SET author=?,body=?,rating=?,source=?,rdate=?,is_published=?,sort=? WHERE id=?')->execute($data);
            } else {
                $pdo->prepare('INSERT INTO reviews (author,body,rating,source,rdate,is_published,sort) VALUES (?,?,?,?,?,?,?)')->execute($data);
            }
            flash('Отзыв сохранён.');
            redirect(admin_url('reviews'));

        case 'articles':
            $action = pv('action');
            if ($action === 'delete') {
                $pdo->prepare('DELETE FROM articles WHERE id = ?')->execute([pint('id')]);
                flash('Статья удалена.');
                redirect(admin_url('articles'));
            }
            $id    = pint('id');
            $title = pv('title');
            $slug  = pv('slug') ?: slugify($title);
            $cover = upload_image('cover_file') ?: pv('cover');
            $data  = [$slug, $title, pv('excerpt'), $_POST['body'] ?? '', $cover, pv('category'),
                pb('is_published'), pv('meta_title'), pv('meta_description')];
            if ($id) {
                $data[] = $id;
                $pdo->prepare('UPDATE articles SET slug=?,title=?,excerpt=?,body=?,cover=?,category=?,is_published=?,meta_title=?,meta_description=? WHERE id=?')->execute($data);
            } else {
                $data[] = now();
                $pdo->prepare('INSERT INTO articles (slug,title,excerpt,body,cover,category,is_published,meta_title,meta_description,published_at) VALUES (?,?,?,?,?,?,?,?,?,?)')->execute($data);
            }
            flash('Статья сохранена.');
            redirect(admin_url('articles'));

        case 'pages':
            $action = pv('action');
            if ($action === 'delete') {
                $pdo->prepare('DELETE FROM pages WHERE id = ?')->execute([pint('id')]);
                flash('Страница удалена.');
                redirect(admin_url('pages'));
            }
            $id    = pint('id');
            $title = pv('title');
            $slug  = pv('slug') ?: slugify($title);
            $data  = [$slug, $title, $_POST['body'] ?? '', pv('meta_title'), pv('meta_description'), pb('is_published'), pint('sort')];
            if ($id) {
                $data[] = $id;
                $pdo->prepare('UPDATE pages SET slug=?,title=?,body=?,meta_title=?,meta_description=?,is_published=?,sort=? WHERE id=?')->execute($data);
            } else {
                $pdo->prepare('INSERT INTO pages (slug,title,body,meta_title,meta_description,is_published,sort) VALUES (?,?,?,?,?,?,?)')->execute($data);
            }
            flash('Страница сохранена.');
            redirect(admin_url('pages'));

        case 'orders':
            $action = pv('action');
            if ($action === 'delete') {
                $pdo->prepare('DELETE FROM orders WHERE id = ?')->execute([pint('id')]);
            } else {
                $pdo->prepare('UPDATE orders SET status = ? WHERE id = ?')->execute([pv('status', 'new'), pint('id')]);
            }
            flash('Заявка обновлена.');
            redirect(admin_url('orders'));

        case 'account':
            $cur = pv('current');
            $new = pv('next');
            if (mb_strlen($new) < 6) {
                flash('Новый пароль должен быть не короче 6 символов.');
                redirect(admin_url('account'));
            }
            if (!password_verify($cur, $user['password_hash'])) {
                flash('Неверный текущий пароль.');
                redirect(admin_url('account'));
            }
            $pdo->prepare('UPDATE users SET password_hash = ? WHERE id = ?')
                ->execute([password_hash($new, PASSWORD_DEFAULT), $user['id']]);
            flash('Пароль изменён.');
            redirect(admin_url('account'));

        case 'home-blocks':
            $action = pv('action');
            if ($action === 'add') {
                $type = pv('section_type', 'custom');
                $types = home_section_types();
                if (!isset($types[$type])) {
                    $type = 'custom';
                }
                $pdo->prepare('INSERT INTO home_sections (section_type, title, subtitle, body, sort, is_active) VALUES (?,?,?,?,?,1)')
                    ->execute([$type, pv('title'), '', pv('body'), pint('sort')]);
                flash('Блок добавлен.');
            } elseif ($action === 'delete') {
                $id = pint('id');
                $st = $pdo->prepare('SELECT section_type FROM home_sections WHERE id = ?');
                $st->execute([$id]);
                $row = $st->fetch();
                if ($row && $row['section_type'] === 'custom') {
                    $pdo->prepare('DELETE FROM home_sections WHERE id = ?')->execute([$id]);
                    flash('Блок удалён.');
                }
            } elseif ($action === 'toggle') {
                $pdo->prepare('UPDATE home_sections SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id = ?')
                    ->execute([pint('id')]);
                flash('Статус блока обновлён.');
            } elseif ($action === 'move') {
                $id = pint('id');
                $dir = pv('dir') === 'down' ? 1 : -1;
                $st = $pdo->prepare('SELECT id, sort FROM home_sections WHERE id = ?');
                $st->execute([$id]);
                $cur = $st->fetch();
                if ($cur) {
                    $cmp = $dir < 0 ? '<' : '>';
                    $ord = $dir < 0 ? 'DESC' : 'ASC';
                    $st2 = $pdo->prepare("SELECT id, sort FROM home_sections WHERE sort $cmp ? ORDER BY sort $ord, id $ord LIMIT 1");
                    $st2->execute([(int) $cur['sort']]);
                    $swap = $st2->fetch();
                    if ($swap) {
                        $pdo->prepare('UPDATE home_sections SET sort = ? WHERE id = ?')->execute([(int) $swap['sort'], $id]);
                        $pdo->prepare('UPDATE home_sections SET sort = ? WHERE id = ?')->execute([(int) $cur['sort'], $swap['id']]);
                    }
                }
                flash('Порядок обновлён.');
            }
            redirect(admin_url('home-blocks'));
    }
}

/* ------------------------------ Rendering ----------------------------- */
$pdo = db();
switch ($p) {
    case 'dashboard':
        render_admin('dashboard', [
            'title'    => 'Обзор',
            'services' => (int) $pdo->query('SELECT COUNT(*) FROM services')->fetchColumn(),
            'diplomas' => (int) $pdo->query('SELECT COUNT(*) FROM diplomas')->fetchColumn(),
            'reviews'  => (int) $pdo->query('SELECT COUNT(*) FROM reviews')->fetchColumn(),
            'articles' => (int) $pdo->query('SELECT COUNT(*) FROM articles')->fetchColumn(),
            'new_orders' => (int) $pdo->query("SELECT COUNT(*) FROM orders WHERE status='new'")->fetchColumn(),
            'paid_orders' => (int) $pdo->query("SELECT COUNT(*) FROM orders WHERE status='paid'")->fetchColumn(),
        ]);
        break;

    case 'home-blocks':
        render_admin('home_blocks', [
            'title' => 'Блоки главной',
            'items' => home_sections_all(),
            'types' => home_section_types(),
        ]);
        break;

    case 'content':
        $page = $_GET['page'] ?? 'home';
        $pages = block_pages();
        if (!isset($pages[$page])) {
            $page = 'home';
        }
        $st = $pdo->prepare('SELECT * FROM content_blocks WHERE page = ? ORDER BY sort ASC');
        $st->execute([$page]);
        render_admin('content', ['title' => 'Тексты страниц', 'page' => $page, 'pages' => $pages, 'blocks' => $st->fetchAll()]);
        break;

    case 'services':
        $edit = null;
        if (!empty($_GET['id'])) {
            $st = $pdo->prepare('SELECT * FROM services WHERE id = ?');
            $st->execute([(int) $_GET['id']]);
            $edit = $st->fetch() ?: null;
        }
        render_admin('services', ['title' => 'Услуги', 'items' => $pdo->query('SELECT * FROM services ORDER BY sort ASC')->fetchAll(), 'edit' => $edit, 'isNew' => isset($_GET['new'])]);
        break;

    case 'diplomas':
        render_admin('diplomas', ['title' => 'Дипломы', 'items' => $pdo->query('SELECT * FROM diplomas ORDER BY sort ASC')->fetchAll()]);
        break;

    case 'education':
        render_admin('education', ['title' => 'Образование', 'items' => $pdo->query('SELECT * FROM education ORDER BY sort ASC')->fetchAll()]);
        break;

    case 'reviews':
        render_admin('reviews', ['title' => 'Отзывы', 'items' => $pdo->query('SELECT * FROM reviews ORDER BY sort ASC')->fetchAll()]);
        break;

    case 'articles':
        $edit = null;
        if (!empty($_GET['id'])) {
            $st = $pdo->prepare('SELECT * FROM articles WHERE id = ?');
            $st->execute([(int) $_GET['id']]);
            $edit = $st->fetch() ?: null;
        }
        render_admin('articles', ['title' => 'Статьи', 'items' => $pdo->query('SELECT * FROM articles ORDER BY published_at DESC')->fetchAll(), 'edit' => $edit, 'isNew' => isset($_GET['new'])]);
        break;

    case 'pages':
        $edit = null;
        if (!empty($_GET['id'])) {
            $st = $pdo->prepare('SELECT * FROM pages WHERE id = ?');
            $st->execute([(int) $_GET['id']]);
            $edit = $st->fetch() ?: null;
        }
        render_admin('pages', ['title' => 'Страницы', 'items' => $pdo->query('SELECT * FROM pages ORDER BY sort ASC')->fetchAll(), 'edit' => $edit, 'isNew' => isset($_GET['new'])]);
        break;

    case 'orders':
        render_admin('orders', ['title' => 'Заявки и оплаты', 'items' => $pdo->query('SELECT * FROM orders ORDER BY created_at DESC')->fetchAll()]);
        break;

    case 'settings':
        render_admin('settings', ['title' => 'Настройки сайта', 's' => all_settings()]);
        break;

    case 'account':
        render_admin('account', ['title' => 'Мой профиль']);
        break;

    default:
        redirect(admin_url());
}
