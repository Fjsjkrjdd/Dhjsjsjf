<?php
$blocks = blocks_for('contacts');
render('contacts', ['blocks' => $blocks, 'page_title' => $blocks['title']]);
