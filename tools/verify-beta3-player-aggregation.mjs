// Real local map demands + SYNTHETIC score-quality fixtures, not real player BP.
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';

const botRoot = process.argv[2];
const reportPath = process.argv[3];
const { aggregatePlayerSkillProfile, demonstratedAxisValue, scoreAchievementQuality, bpRankWeight }
  = await import(pathToFileURL(path.join(botRoot, 'server/bots/playerSkillProfile.ts')).href);
const report = JSON.parse(await fs.readFile(reportPath, 'utf8'));
const samples = report.results.slice(0, 50);
assert.equal(samples.length, 50);
const qualities = {
  strong: scoreAchievementQuality({ accuracy: .995, perfect: true, max_combo: 1000,
    beatmap: { max_combo: 1000 }, statistics: { count_300: 995, count_100: 5, count_miss: 0 } }),
  weak: scoreAchievementQuality({ accuracy: .85, perfect: false, max_combo: 300,
    beatmap: { max_combo: 1000 }, statistics: { count_300: 800, count_100: 180, count_miss: 20 } }),
};
const result = {};
for (const [name, quality] of Object.entries(qualities)) {
  const aggregates = {};
  for (const version of ['before', 'after']) {
    const analyzed = samples.map((sample, i) => ({ rank: i + 1, weight: bpRankWeight(i + 1),
      scoreQuality: quality, primaryType: 'BALANCED',
      axes: Object.fromEntries(Object.entries(sample[version]).map(([axis, value]) => [axis, demonstratedAxisValue(axis, value, quality)])),
    }));
    aggregates[version] = aggregatePlayerSkillProfile(analyzed);
  }
  for (const old of aggregates.before.axes) {
    if (old.key !== 'spatial_precision') assert.deepEqual(aggregates.after.axes.find(a => a.key === old.key), old);
  }
  result[name] = Object.fromEntries(['before', 'after'].map(v => [v, aggregates[v].axes.find(a => a.key === 'spatial_precision')]));
}
assert.ok(result.strong.after.ceiling > result.weak.after.ceiling);
assert.ok(result.strong.after.median > result.weak.after.median);
console.log(JSON.stringify({ scope: 'Synthetic BP50 quality fixtures over real local map demands; not current player data', result, otherEightUnchanged: true }, null, 2));
process.exit(0);
