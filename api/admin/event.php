<?php
declare(strict_types=1);

require_once __DIR__ . '/../../backend/bootstrap.php';

$user = sk_require_user();
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$id = trim((string) ($_GET['id'] ?? ''));

if ($id === '') {
    sk_json(['error' => 'missing_id'], 400);
}

$db = sk_db();

if ($method === 'GET') {
    $event = sk_event_snapshot($db, $id);
    if (!$event) {
        sk_json(['error' => 'not_found'], 404);
    }
    sk_json(['event' => $event]);
}

if ($method !== 'PUT') {
    sk_json(['error' => 'method_not_allowed'], 405);
}

$body = sk_body();
$allowedStatuses = ['active', 'cancelled', 'hidden'];
$allowedReview = ['automatic', 'human_reviewed'];
$allowedCategories = ['rail','bus','tram','trolleybus','metro','water','air','cableway','other'];

$current = sk_event_snapshot($db, $id);
if (!$current) {
    sk_json(['error' => 'not_found'], 404);
}

$status = in_array(($body['status'] ?? ''), $allowedStatuses, true) ? $body['status'] : $current['status'];
$reviewStatus = in_array(($body['review_status'] ?? ''), $allowedReview, true) ? $body['review_status'] : 'human_reviewed';
$categories = array_values(array_unique(array_filter((array) ($body['categories'] ?? $current['categories']), fn($v) => in_array($v, $allowedCategories, true))));

$db->beginTransaction();
try {
    $stmt = $db->prepare('UPDATE events SET title=?, description=?, city=?, place=?, region=?, time_start=?, time_end=?, public_url=?, status=?, review_status=?, source_kind="manual" WHERE id=?');
    $stmt->execute([
        trim((string) ($body['title'] ?? $current['title'])),
        $body['description'] ?? $current['description'],
        $body['city'] ?? $current['city'],
        $body['place'] ?? $current['place'],
        $body['region'] ?? $current['region'],
        $body['time_start'] ?? $current['time_start'],
        $body['time_end'] ?? $current['time_end'],
        $body['public_url'] ?? $current['public_url'],
        $status,
        $reviewStatus,
        $id,
    ]);

    $db->prepare('DELETE FROM event_categories WHERE event_id=?')->execute([$id]);
    $insertCategory = $db->prepare('INSERT INTO event_categories (event_id, category) VALUES (?, ?)');
    foreach ($categories as $category) {
        $insertCategory->execute([$id, $category]);
    }

    if (isset($body['dates']) && is_array($body['dates'])) {
        $db->prepare('DELETE FROM event_dates WHERE event_id=?')->execute([$id]);
        $insertDate = $db->prepare('INSERT INTO event_dates (event_id, starts_on, ends_on, starts_at, ends_at, sort_order) VALUES (?, ?, ?, ?, ?, ?)');
        foreach ($body['dates'] as $i => $date) {
            if (empty($date['starts_on'])) continue;
            $insertDate->execute([$id, $date['starts_on'], $date['ends_on'] ?? $date['starts_on'], $date['starts_at'] ?? null, $date['ends_at'] ?? null, $i]);
        }
    }

    $snapshot = sk_event_snapshot($db, $id);
    $revision = $db->prepare('INSERT INTO event_revisions (event_id, actor_type, actor_user_id, action, snapshot_json, note) VALUES (?, "user", ?, ?, ?, ?)');
    $action = $status === 'cancelled' ? 'cancel' : ($status === 'hidden' ? 'hide' : 'update');
    $revision->execute([$id, $user['id'], $action, json_encode($snapshot, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES), $body['note'] ?? null]);

    $db->commit();
    sk_json(['event' => $snapshot]);
} catch (Throwable $e) {
    $db->rollBack();
    sk_json(['error' => 'server_error'], 500);
}
