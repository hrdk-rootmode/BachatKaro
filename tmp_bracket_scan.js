const fs = require('fs');
const s = fs.readFileSync('src/screens/product/ProductDetailScreen.jsx', 'utf8');
let line = 1;
let col = 0;
let state = 'code';
let quote = '';
let esc = false;
const stack = [];
const push = (ch) => stack.push({ ch, line, col });
const pop = (expect) => {
  if (!stack.length) {
    console.log('extra closing', expect, 'at', line + ':' + col);
    return;
  }
  const top = stack[stack.length - 1];
  const ok = (top.ch === '(' && expect === ')') || (top.ch === '{' && expect === '}') || (top.ch === '[' && expect === ']');
  if (ok) {
    stack.pop();
  } else {
    console.log('mismatch close', expect, 'at', line + ':' + col, 'top', top.ch, 'opened at', top.line + ':' + top.col);
  }
};
for (let i = 0; i < s.length; i++) {
  const ch = s[i];
  const nx = s[i + 1];
  col++;
  if (ch === '\n') {
    line++;
    col = 0;
  }
  if (state === 'line') {
    if (ch === '\n') state = 'code';
    continue;
  }
  if (state === 'block') {
    if (ch === '*' && nx === '/') {
      state = 'code';
      i++;
      col++;
    }
    continue;
  }
  if (state === 'str') {
    if (esc) {
      esc = false;
      continue;
    }
    if (ch === '\\') {
      esc = true;
      continue;
    }
    if (ch === quote) {
      state = 'code';
      quote = '';
    }
    continue;
  }
  if (state === 'template') {
    if (esc) {
      esc = false;
      continue;
    }
    if (ch === '\\') {
      esc = true;
      continue;
    }
    if (ch === '`') {
      state = 'code';
      continue;
    }
    continue;
  }
  if (ch === '/' && nx === '/') {
    state = 'line';
    i++;
    col++;
    continue;
  }
  if (ch === '/' && nx === '*') {
    state = 'block';
    i++;
    col++;
    continue;
  }
  if (ch === '\'' || ch === '"') {
    state = 'str';
    quote = ch;
    continue;
  }
  if (ch === '`') {
    state = 'template';
    continue;
  }
  if (ch === '(' || ch === '{' || ch === '[') push(ch);
  else if (ch === ')' || ch === '}' || ch === ']') pop(ch);
}
console.log('remaining', stack.length);
if (stack.length) {
  console.log('last 20 opens:');
  stack.slice(-20).forEach((x) => console.log(x.ch, 'opened at', x.line + ':' + x.col));
}
