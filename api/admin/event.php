<?php
declare(strict_types=1);
require_once __DIR__ . '/../../backend/bootstrap.php';
$user=sk_require_user();$method=$_SERVER['REQUEST_METHOD']??'GET';$id=(int)($_GET['id']??0);if(!$id)sk_json(['error'=>'missing_id'],400);$db=sk_db();
if($method==='GET'){if(!$e=sk_event_snapshot($db,(string)$id))sk_json(['error'=>'not_found'],404);sk_json(['event'=>$e]);}
if($method!=='PUT')sk_json(['error'=>'method_not_allowed'],405);
$b=sk_body();$current=sk_event_snapshot($db,(string)$id);if(!$current)sk_json(['error'=>'not_found'],404);
$statuses=['active','cancelled','hidden'];$reviews=['automatic','human_reviewed'];$cats=['rail','bus','tram','trolleybus','metro','water','air','cableway','other'];
$status=in_array(($b['status']??''),$statuses,true)?$b['status']:$current['status'];$review=in_array(($b['review_status']??''),$reviews,true)?$b['review_status']:'human_reviewed';$categories=array_values(array_unique(array_filter((array)($b['categories']??$current['categories']),fn($v)=>in_array($v,$cats,true))));
$db->beginTransaction();try{
 $q=$db->prepare('UPDATE events SET title=?,description=?,city=?,place=?,region=?,country=?,route=?,organizer=?,time_start=?,time_end=?,all_day=?,public_url=?,status=?,review_status=?,source_kind="manual" WHERE id=?');
 $q->execute([trim((string)($b['title']??$current['title'])),$b['description']??$current['description'],$b['city']??$current['city'],$b['place']??$current['place'],$b['region']??$current['region'],$b['country']??$current['country'],$b['route']??$current['route'],$b['organizer']??$current['organizer'],$b['time_start']??$current['time_start'],$b['time_end']??$current['time_end'],!empty($b['all_day'])?1:0,$b['public_url']??$current['public_url'],$status,$review,$id]);
 $db->prepare('DELETE FROM event_categories WHERE event_id=?')->execute([$id]);$qc=$db->prepare('INSERT INTO event_categories(event_id,category) VALUES (?,?)');foreach($categories as $c)$qc->execute([$id,$c]);
 if(isset($b['dates'])&&is_array($b['dates'])){$db->prepare('DELETE FROM event_dates WHERE event_id=?')->execute([$id]);$qd=$db->prepare('INSERT INTO event_dates(event_id,starts_on,ends_on,starts_at,ends_at,sort_order) VALUES (?,?,?,?,?,?)');foreach($b['dates'] as $i=>$d){if(empty($d['starts_on']))continue;$qd->execute([$id,$d['starts_on'],$d['ends_on']??$d['starts_on'],$d['starts_at']??null,$d['ends_at']??null,$i]);}}
 if(array_key_exists('public_url',$b)){$db->prepare('DELETE FROM event_sources WHERE event_id=? AND is_primary=1')->execute([$id]);if(!empty($b['public_url']))$db->prepare('INSERT INTO event_sources(event_id,url,is_primary) VALUES (?,?,1)')->execute([$id,$b['public_url']]);}
 $snap=sk_event_snapshot($db,(string)$id);$action=$status==='cancelled'?'cancel':($status==='hidden'?'hide':'update');$rev=$db->prepare('INSERT INTO event_revisions(event_id,actor_type,actor_user_id,action,snapshot_json,note) VALUES (?,"user",?,?,?,?)');$rev->execute([$id,$user['id'],$action,json_encode($snap,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES),$b['note']??null]);$db->commit();sk_json(['event'=>$snap]);
}catch(Throwable $e){$db->rollBack();sk_json(['error'=>'server_error'],500);}
