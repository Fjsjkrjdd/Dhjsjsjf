<?php
/** @var array $blocks $services $diplomas $reviews $sections $articles */
require_once __DIR__ . '/../includes/yookassa.php';
$support_reasons = [
    ['01', 'Когда тревога и напряжение не отпускают', 'Мысли ходят по кругу, тело постоянно в тонусе, а отдых не возвращает силы. На консультации можно остановиться и понять, что с вами происходит.'],
    ['02', 'Когда отношения стали источником боли', 'Ссоры, холод, обида, недоверие или ощущение одиночества рядом с близким человеком — с этим можно работать бережно и без обвинений.'],
    ['03', 'Когда сложно опираться на себя', 'Неуверенность, вина, стыд, страх проявляться и выбирать себя часто мешают жить свободно. Мы будем искать вашу внутреннюю опору.'],
    ['04', 'Когда повторяются одни и те же сценарии', 'Похожие конфликты, выбор неподходящих отношений или постоянное напряжение могут стать понятнее, если увидеть их причины.'],
];
$approach = [
    'Клиническая психология и бережная диагностика состояния',
    'Системная семейная терапия для отношений, пар и семей',
    'ACT — терапия принятия и ответственности',
    'Эмоционально-фокусированный и арт-терапевтический подход',
];
$first_meeting = [
    ['Обсуждаем ваш запрос', 'Вы рассказываете о ситуации в своём темпе — без давления, оценок и необходимости «говорить правильно».'],
    ['Проясняем главное', 'Вместе отделяем факты, чувства и потребности, чтобы увидеть проблему объёмнее и спокойнее.'],
    ['Намечаем шаги', 'Я объясняю, какой формат работы может подойти и на что мы будем опираться дальше.'],
    ['Проверяем контакт', 'Вы понимаете, комфортен ли вам мой стиль работы. Решение продолжать всегда остаётся за вами.'],
];
$links = social_links();
$home_hero = 'uploads/home-hero.jpg';
$home_about = 'uploads/home-about.jpg';
$bookable = array_values(array_filter($services, static fn($s) => !empty($s['is_bookable'])));
?>
<section id="home" class="landing-hero">
    <div class="landing-hero-bg"></div>
    <div class="container landing-hero-grid">
        <div class="landing-hero-copy">
            <p class="landing-kicker">Психолог онлайн и очно</p>
            <h1><?= e(setting('owner_name')) ?></h1>
            <h2>Работа с тревогой, самооценкой и кризисами в отношениях</h2>
            <p class="landing-lead"><?= e($blocks['hero_subtitle']) ?></p>
            <div class="landing-actions">
                <a href="#landing-booking" class="landing-btn landing-btn-dark">Записаться на консультацию</a>
                <a href="<?= e(tel_href(setting('phone'))) ?>" class="landing-phone"><?= e(setting('phone')) ?></a>
            </div>
            <?php require __DIR__ . '/partials/social_bar.php'; ?>
        </div>
        <div class="landing-portrait-wrap">
            <span class="landing-orbit landing-orbit-one"></span>
            <span class="landing-orbit landing-orbit-two"></span>
            <figure class="landing-portrait">
                <img src="<?= e(asset($home_hero)) ?>" alt="<?= e(setting('owner_name')) ?>">
            </figure>
        </div>
    </div>
</section>

<section id="landing-booking" class="landing-booking-section">
    <div class="container landing-booking-grid">
        <aside class="landing-dark-card">
            <p class="landing-kicker">Можно начать с малого</p>
            <h2>Иногда самый сложный шаг — написать.</h2>
            <p>Оставьте заявку — я свяжусь с вами, помогу выбрать формат консультации и отвечу на вопросы.</p>
            <a href="<?= e(tel_href(setting('phone'))) ?>" class="landing-card-phone"><?= e(setting('phone')) ?></a>
            <?php require __DIR__ . '/partials/social_bar.php'; ?>
        </aside>
        <form class="landing-form landing-short-form booking-form" method="post" action="<?= e(url('booking/submit')) ?>">
            <p class="form-title">Форма заявки сайт</p>
            <label class="field"><span>Ваше имя</span><input type="text" name="name" required></label>
            <label class="field"><span>Телефон</span><input type="tel" name="phone" required></label>
            <label class="field"><span>Какой у Вас запрос?</span><textarea name="comment" rows="5"></textarea></label>
            <label class="check-box"><input type="checkbox" name="agree" value="1" required><span>Я ознакомлен с <a href="<?= e(url('privacy')) ?>">политикой конфиденциальности</a> и даю согласие на обработку персональных данных.</span></label>
            <button type="submit" class="landing-btn landing-btn-dark landing-btn-block">Отправить</button>
        </form>
    </div>
</section>

<section id="about" class="container landing-about">
    <div class="landing-about-photo">
        <img src="<?= e(asset($home_about)) ?>" alt="<?= e(setting('owner_name')) ?>">
    </div>
    <div>
        <p class="landing-kicker">Давайте знакомиться</p>
        <h2>Я — <?= e(setting('owner_name')) ?>, <?= e(function_exists('mb_strtolower') ? mb_strtolower(setting('profession') ?: 'психолог') : (setting('profession') ?: 'психолог')) ?>.</h2>
        <p class="landing-text">Провожу консультации для взрослых, пар и семей онлайн, а также работаю очно в Ростове-на-Дону. Моя задача — помочь вам услышать себя и вернуть ощущение опоры.</p>
        <div class="landing-reasons"><?php foreach ($support_reasons as $item): ?><article><span><?= e($item[0]) ?></span><h3><?= e($item[1]) ?></h3><p><?= e($item[2]) ?></p></article><?php endforeach; ?></div>
    </div>
</section>

<section class="landing-stats"><div class="container"><div><strong>700+</strong><span>часов профильного обучения</span></div><div><strong>5+</strong><span>лет практики</span></div><div><strong>100%</strong><span>конфиденциальность</span></div><div><strong>30</strong><span>минут на первую встречу</span></div></div></section>

<section class="landing-photo-strip" aria-label="Фотографии кабинета и психолога">
    <div class="container">
        <img src="<?= e(asset($home_hero)) ?>" alt="<?= e(setting('owner_name')) ?>">
        <img src="<?= e(asset($home_about)) ?>" alt="Кабинет психолога">
        <img src="<?= e(asset($home_hero)) ?>" alt="<?= e(setting('owner_name')) ?>">
        <img src="<?= e(asset($home_about)) ?>" alt="Пространство консультаций">
    </div>
</section>

<section id="approach" class="container landing-approach">
    <div>
        <p class="landing-kicker">Как проходит работа с психологом</p>
        <h2>Мой подход</h2>
        <p class="landing-text">Я работаю спокойно, бережно и без оценок. Важно не «чинить» человека, а помочь ему понять свои реакции, увидеть повторяющиеся сценарии и найти новые способы быть с собой и близкими.</p>
        <ul><?php foreach ($approach as $item): ?><li><?= e($item) ?></li><?php endforeach; ?></ul>
    </div>
    <figure><img src="<?= e(asset($home_about)) ?>" alt="<?= e(setting('owner_name')) ?>"></figure>
</section>

<section class="landing-psych container">
    <figure><img src="<?= e(asset($home_hero)) ?>" alt="<?= e(setting('owner_name')) ?>"></figure>
    <div>
        <p class="landing-kicker">О психологе</p>
        <h2><?= e(setting('owner_name')) ?></h2>
        <p class="landing-text"><?= e(setting('profession')) ?>, психолог-консультант. Работаю онлайн по всей России и очно в Ростове-на-Дону.</p>
        <p class="landing-text">Образование и сертификаты можно редактировать в админке — блоки сайта сохраняют структуру PHP-основы и используют ваши данные.</p>
    </div>
</section>

<section class="landing-repeat" id="landing-repeat">
    <div class="container landing-booking-grid">
        <aside class="landing-dark-card">
            <p class="landing-kicker">Можно начать с малого</p>
            <h2>Иногда самый сложный шаг — написать.</h2>
            <p>Вы можете записаться на первую консультацию психолога онлайн и спокойно разобраться в своём состоянии.</p>
        </aside>
        <form class="landing-form landing-short-form booking-form" method="post" action="<?= e(url('booking/submit')) ?>">
            <p class="form-title">Форма заявки сайт</p>
            <label class="field"><span>Ваше имя</span><input type="text" name="name" required></label>
            <label class="field"><span>Телефон</span><input type="tel" name="phone" required></label>
            <label class="field"><span>Какой у Вас запрос?</span><textarea name="comment" rows="5"></textarea></label>
            <label class="check-box"><input type="checkbox" name="agree" value="1" required><span>Я ознакомлен с <a href="<?= e(url('privacy')) ?>">политикой конфиденциальности</a> и даю согласие на обработку персональных данных.</span></label>
            <button type="submit" class="landing-btn landing-btn-dark landing-btn-block">Отправить</button>
        </form>
    </div>
</section>

<?php if ($services): ?>
<section id="services" class="landing-services">
    <div class="container">
        <p class="landing-kicker center">Услуги</p>
        <h2>Форматы консультаций</h2>
        <div class="cards-grid"><?php foreach (array_slice($services, 0, 6) as $s): require __DIR__ . '/partials/service_card.php'; endforeach; ?></div>
    </div>
</section>
<?php endif; ?>

<section id="first-meeting" class="container landing-first">
    <p class="landing-kicker">Первая консультация</p>
    <h2>Первая встреча — это 30 минут, где мы:</h2>
    <div><?php foreach ($first_meeting as $i => $item): ?><article><span><?= $i + 1 ?></span><h3><?= e($item[0]) ?></h3><p><?= e($item[1]) ?></p></article><?php endforeach; ?></div>
</section>

<?php if (!empty($articles)): ?>
<section class="landing-blog"><div class="container"><p class="landing-kicker">Блог</p><h2>Спокойно о сложном</h2><div class="articles-grid"><?php foreach ($articles as $a): ?><article class="card article-card"><a href="<?= e(url('articles/' . $a['slug'])) ?>" class="article-cover"><?php if ($a['cover']): ?><img src="<?= e(asset($a['cover'])) ?>" alt="<?= e($a['title']) ?>"><?php else: ?><span class="cover-stub">Статья</span><?php endif; ?></a><div class="article-body"><span class="article-cat"><?= e($a['category']) ?></span><h2><a href="<?= e(url('articles/' . $a['slug'])) ?>"><?= e($a['title']) ?></a></h2></div></article><?php endforeach; ?></div></div></section>
<?php endif; ?>

<section class="landing-quote-strip">
    <div class="container">
        <img src="<?= e(asset($home_about)) ?>" alt="<?= e(setting('owner_name')) ?>">
        <div>
            <p>Иногда путь к спокойствию начинается не с силы, а с разрешения быть уязвимой.</p>
            <p>Работа с психологом — это не про исправление себя, а про возвращение к себе настоящей.</p>
            <p>Когда рядом появляется поддержка, даже самые сложные чувства перестают быть такими пугающими.</p>
        </div>
    </div>
</section>

<section id="contacts" class="landing-contacts"><div class="container"><div><p class="landing-kicker">Связаться со мной</p><h2>Вы можете написать или позвонить мне в удобном формате.</h2><p>Я отвечаю лично и стараюсь делать это в течение дня.</p><a href="<?= e(tel_href(setting('phone'))) ?>" class="landing-contact-phone"><?= e(setting('phone')) ?></a><?php require __DIR__ . '/partials/social_bar.php'; ?></div><blockquote>Я не исправляю людей — я помогаю им бережно вернуть связь с собой.</blockquote></div></section>
