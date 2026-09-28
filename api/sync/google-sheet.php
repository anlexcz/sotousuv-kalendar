<?php
declare(strict_types=1);

require_once __DIR__ . '/../../backend/bootstrap.php';

$config = sk_config();
$token = (string)($_SERVER['HTTP_X_SYNC_TOKEN'] ?? '');
if ($config['sheet_sync_token'] === '' || !hash_equals((string)$config['sheet_sync_token'], $token)) {
    sk_json(['error' => 'unauthorized'], 401);
}
if (($_SERVER['REQUEST_METHOD'] ?? 'GET') !== 'POST') sk_json(['error' => 'method_not_allowed'], 405);

$body = sk_body();
$rows = $body['rows'] ?? null;
if (!is_array($rows)) sk_json(['error' => 'invalid_rows'], 400);

function sk_sheet_bool(mixed $v): bool { return in_array(mb_strtoupper(trim((string)$v)), ['ANO','TRUE','1','YES'], true); }
function sk_sheet_status(string $v): string {
    $v = mb_strtoupper(trim($v));
    if (str_contains($v, 'ZRUŠ')) return 'cancelled';
    if (str_contains($v, 'SKRY')) return 'hidden';
    return 'active';
}
function sk_sheet_categories(string $value): array {
    $s = mb_strtolower($value);
    $map = ['rail'=>['želez','vlak','úzkokolej'],'bus'=>['autobus'],'tram'=>['tramvaj'],'trolleybus'=>['trolejbus'],'metro'=>['metro'],'water'=>['loď','lodní'],'air'=>['letad','letec'],'cableway'=>['lanov']];
    $out=[]; foreach($map as $id=>$needles){ foreach($needles as $n){ if(str_contains($s,$n)){ $out[]=$id; break; } } }
    return $out ?: ['other'];
}
function sk_iso_date(?string $s): ?string {
    if (!$s) return null;
    $s=trim($s);
    foreach(['!Y-m-d','!j. n. Y','!j.n.Y'] as $f){$d=DateTimeImmutable::createFromFormat($f,$s);if($d)return $d->format('Y-m-d');}
    return null;
}
function sk_explicit_dates(array $row): array {
    $raw=trim((string)($row['Termíny'] ?? $row['Termíny série'] ?? ''));
    $fallbackFrom=sk_iso_date((string)($row['Datum od'] ?? ''));
    $fallbackTo=sk_iso_date((string)($row['Datum do'] ?? '')) ?: $fallbackFrom;
    if($raw==='') return $fallbackFrom ? [['starts_on'=>$fallbackFrom,'ends_on'=>$fallbackTo]] : [];

    // Synchronizer accepts canonical YYYY-MM-DD or YYYY-MM-DD..YYYY-MM-DD tokens separated by semicolons.
    // Human Czech notation is deliberately not guessed here; Apps Script normalizes it before sending.
    $out=[];
    foreach(array_filter(array_map('trim',explode(';',$raw))) as $token){
        if(preg_match('/^(\d{4}-\d{2}-\d{2})(?:\.\.(\d{4}-\d{2}-\d{2}))?$/',$token,$m)){
            $out[]=['starts_on'=>$m[1],'ends_on'=>$m[2] ?: $m[1]];
        }
    }
    return $out ?: ($fallbackFrom ? [['starts_on'=>$fallbackFrom,'ends_on'=>$fallbackTo]] : []);
}
function sk_row_snapshot(array $row): array {
    $sources=array_values(array_filter([trim((string)($row['Hlavní zdroj']??'')),trim((string)($row['Ověřovací zdroj']??''))]));
    return [
        'title'=>trim((string)($row['Název akce']??'')),
        'description'=>trim((string)($row['Stručný popis']??'')) ?: null,
        'city'=>trim((string)($row['Obec']??'')) ?: null,
        'place'=>trim((string)($row['Místo']??'')) ?: null,
        'region'=>trim((string)($row['Kraj / region']??'')) ?: null,
        'country'=>trim((string)($row['Stát']??'')) ?: null,
        'route'=>trim((string)($row['Trasa']??'')) ?: null,
        'organizer'=>trim((string)($row['Pořadatel']??'')) ?: null,
        'time_start'=>trim((string)($row['Čas od']??'')) ?: null,
        'time_end'=>trim((string)($row['Čas do']??'')) ?: null,
        'all_day'=>sk_sheet_bool($row['Celodenní']??'ANO') ? 1 : 0,
        'status'=>sk_sheet_status((string)($row['Stav akce']??'')),
        'categories'=>sk_sheet_categories((string)($row['Druh dopravy']??'')),
        'dates'=>sk_explicit_dates($row),
        'locations'=>array_values(array_filter(array_map('trim',preg_split('/\s*\/\s*/',(string)($row['Obec']??'')) ?: []))),
        'sources'=>$sources,
    ];
}

$db=sk_db(); $created=0;$updated=0;$proposals=0;$skipped=0;$warnings=[];
foreach($rows as $i=>$row){
    if(!is_array($row)) continue;
    $external=trim((string)($row['ID']??''));
    $incoming=sk_row_snapshot($row);
    if($external==='' || $incoming['title']===''){ $skipped++; continue; }
    if(!$incoming['dates']) $warnings[]=['row'=>$i+2,'id'=>$external,'warning'=>'missing_dates'];

    $q=$db->prepare('SELECT id,source_kind,review_status FROM events WHERE source_system="google_sheet" AND source_external_id=?');
    $q->execute([$external]); $existing=$q->fetch();

    if(!$existing){
        $db->beginTransaction();
        try{
            $ins=$db->prepare('INSERT INTO events (source_system,source_external_id,title,description,city,place,region,country,route,organizer,time_start,time_end,all_day,status,review_status,source_kind,source_last_checked_at) VALUES ("google_sheet",?,?,?,?,?,?,?,?,?,?,?,?,?,"automatic","import",NOW())');
            $ins->execute([$external,$incoming['title'],$incoming['description'],$incoming['city'],$incoming['place'],$incoming['region'],$incoming['country'],$incoming['route'],$incoming['organizer'],$incoming['time_start'],$incoming['time_end'],$incoming['all_day'],$incoming['status']]);
            $id=(int)$db->lastInsertId(); sk_apply_sheet_children($db,$id,$incoming);
            $snap=sk_event_snapshot($db,(string)$id);
            $db->prepare('INSERT INTO event_revisions(event_id,actor_type,action,snapshot_json,note) VALUES (?,"import","import",?,?)')->execute([$id,json_encode($snap,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES),'První import z Google tabulky']);
            $db->commit();$created++;
        }catch(Throwable $e){$db->rollBack();throw $e;}
        continue;
    }

    $id=(int)$existing['id']; $current=sk_event_snapshot($db,(string)$id);
    $proposed=sk_sheet_comparable($incoming); $currentCmp=sk_event_comparable($current);
    if($proposed==$currentCmp){$db->prepare('UPDATE events SET source_last_checked_at=NOW() WHERE id=?')->execute([$id]);continue;}

    if($existing['source_kind']==='manual' || $existing['review_status']==='human_reviewed'){
        $changes=[];foreach($proposed as $k=>$v)if(($currentCmp[$k]??null)!=$v)$changes[$k]=['current'=>$currentCmp[$k]??null,'proposed'=>$v];
        $severity=array_intersect(array_keys($changes),['dates','city','place','status'])?'important':'normal';
        $db->prepare('INSERT INTO event_change_proposals(event_id,status,severity,proposed_json,detected_changes_json) VALUES (?,"pending",?,?,?)')->execute([$id,$severity,json_encode($incoming,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES),json_encode($changes,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES)]);
        $db->prepare('UPDATE events SET source_last_checked_at=NOW() WHERE id=?')->execute([$id]);$proposals++;
    }else{
        sk_apply_sheet_event($db,$id,$incoming);$updated++;
    }
}
sk_json(compact('created','updated','proposals','skipped','warnings'));

function sk_sheet_comparable(array $e): array { return ['title'=>$e['title'],'description'=>$e['description'],'city'=>$e['city'],'place'=>$e['place'],'region'=>$e['region'],'country'=>$e['country'],'route'=>$e['route'],'organizer'=>$e['organizer'],'time_start'=>$e['time_start'],'time_end'=>$e['time_end'],'all_day'=>$e['all_day'],'status'=>$e['status'],'categories'=>$e['categories'],'dates'=>$e['dates'],'sources'=>$e['sources']]; }
function sk_event_comparable(array $e): array { return ['title'=>$e['title'],'description'=>$e['description'],'city'=>$e['city'],'place'=>$e['place'],'region'=>$e['region'],'country'=>$e['country'],'route'=>$e['route'],'organizer'=>$e['organizer'],'time_start'=>$e['time_start'],'time_end'=>$e['time_end'],'all_day'=>(int)$e['all_day'],'status'=>$e['status'],'categories'=>$e['categories'],'dates'=>array_map(fn($d)=>['starts_on'=>$d['starts_on'],'ends_on'=>$d['ends_on']],$e['dates']),'sources'=>array_map(fn($s)=>$s['url'],$e['sources'])]; }
function sk_apply_sheet_children(PDO $db,int $id,array $e): void {
    foreach(['event_dates','event_categories','event_locations','event_sources'] as $t)$db->prepare("DELETE FROM $t WHERE event_id=?")->execute([$id]);
    $q=$db->prepare('INSERT INTO event_dates(event_id,starts_on,ends_on,starts_at,ends_at,sort_order) VALUES (?,?,?,?,?,?)');foreach($e['dates'] as $i=>$d)$q->execute([$id,$d['starts_on'],$d['ends_on'],$e['time_start'],$e['time_end'],$i]);
    $q=$db->prepare('INSERT INTO event_categories(event_id,category) VALUES (?,?)');foreach($e['categories'] as $c)$q->execute([$id,$c]);
    $q=$db->prepare('INSERT INTO event_locations(event_id,label,sort_order) VALUES (?,?,?)');foreach($e['locations'] as $i=>$l)$q->execute([$id,$l,$i]);
    $q=$db->prepare('INSERT INTO event_sources(event_id,url,is_primary,last_seen_at) VALUES (?,?,?,NOW())');foreach($e['sources'] as $i=>$u)$q->execute([$id,$u,$i===0?1:0]);
}
function sk_apply_sheet_event(PDO $db,int $id,array $e): void {
    $db->beginTransaction();try{
        $q=$db->prepare('UPDATE events SET title=?,description=?,city=?,place=?,region=?,country=?,route=?,organizer=?,time_start=?,time_end=?,all_day=?,status=?,source_kind="import",source_last_checked_at=NOW() WHERE id=?');
        $q->execute([$e['title'],$e['description'],$e['city'],$e['place'],$e['region'],$e['country'],$e['route'],$e['organizer'],$e['time_start'],$e['time_end'],$e['all_day'],$e['status'],$id]);sk_apply_sheet_children($db,$id,$e);
        $snap=sk_event_snapshot($db,(string)$id);$db->prepare('INSERT INTO event_revisions(event_id,actor_type,action,snapshot_json,note) VALUES (?,"import","import",?,?)')->execute([$id,json_encode($snap,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES),'Automatická synchronizace z Google tabulky']);$db->commit();
    }catch(Throwable $ex){$db->rollBack();throw $ex;}
}
