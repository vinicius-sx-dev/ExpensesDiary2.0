import {test} from 'node:test';
import assert from 'node:assert/strict';
import {cents,isoDate} from '../src/lib/types.ts';
test('parses Brazilian money without floating point drift',()=>{assert.equal(cents('0,29'),29);assert.equal(cents('12.50'),1250);assert.equal(cents('100'),10000);});
test('rejects ambiguous, negative and excessive values',()=>{for(const value of ['1.000,00','1,000','-2','0','Infinity','1e3','100000001,00'])assert.throws(()=>cents(value));});
test('validates real calendar dates',()=>{assert.equal(isoDate('2024-02-29'),'2024-02-29');for(const value of ['2025-02-29','2026-13-01','12/11/2026'])assert.throws(()=>isoDate(value));});
