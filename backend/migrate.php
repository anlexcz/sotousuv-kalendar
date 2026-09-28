<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
require_once __DIR__.'/db.php';
$db=sk_db();$files=glob(__DIR__.'/migrations/*.sql')?:[];sort($files);
foreach($files as $file){
 echo 'Applying '.basename($file).PHP_EOL;
 $sql=file_get_contents($file);if($sql===false)throw new RuntimeException('Cannot read '.$file);
 $statements=preg_split('/;\s*(?:\r?\n|$)/',$sql)?:[];
 foreach($statements as $statement){$statement=trim($statement);if($statement!=='')$db->exec($statement);}
}
echo "Done.\n";
