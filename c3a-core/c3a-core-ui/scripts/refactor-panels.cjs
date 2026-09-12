const fs = require('fs');
const ts = require('typescript');
const vm = require('vm');
const source = fs.readFileSync('src/screens/VisitScreen.tsx', 'utf8');
const ast = ts.createSourceFile('screen.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const wanted = new Set(['FinishVisitFormModal','RiskReviewModal','TranslationTab','PatientDetailsPanel','VisitSummaryPanel','createEmptyCareOutcomeForm','isCareOutcomeFormComplete']);
const roots = [...wanted];
const declarations = new Map();
for (const node of ast.statements) {
  const name = node.name?.text ?? (ts.isVariableStatement(node) ? node.declarationList.declarations[0].name.getText(ast) : undefined);
  if (name) declarations.set(name, node);
}
function collect(name) {
 const node=declarations.get(name); if(!node)return;
 function visit(n){if(ts.isIdentifier(n)&&declarations.has(n.text)&&!wanted.has(n.text)){wanted.add(n.text);collect(n.text);}ts.forEachChild(n,visit);}
 ts.forEachChild(node,visit);
}
roots.forEach(collect);
let result=ast.statements.filter(n=>ts.isImportDeclaration(n)||[...declarations].some(([k,v])=>v===n&&wanted.has(k))).map(n=>n.getFullText(ast)).join('\n');
result += '\nexport { '+roots.join(', ')+' };\n';
fs.writeFileSync('src/screens/CarePanels.tsx',result);
const palette={'#F7FAF8':'care-canvas','#F5FAFA':'care-canvas','#F0F7F7':'care-canvas','#FFFFFF':'white','#16231E':'care-ink','#1A2B2B':'care-ink','#60746B':'care-muted','#2E6F73':'care-primary','#0D7377':'care-primary','#D9E2DE':'care-line','#E4ECE8':'care-line','#D5E8E8':'care-line','#F4F7F6':'care-soft','#E8EFEA':'care-soft','#E8F4F4':'care-soft','#9A6A13':'care-amber','#A83B32':'care-danger'};
const dim={padding:'p',paddingHorizontal:'px',paddingVertical:'py',paddingTop:'pt',paddingBottom:'pb',paddingLeft:'pl',paddingRight:'pr',margin:'m',marginHorizontal:'mx',marginVertical:'my',marginTop:'mt',marginBottom:'mb',marginLeft:'ml',marginRight:'mr',gap:'gap',rowGap:'gap-y',columnGap:'gap-x',width:'w',height:'h',minWidth:'min-w',minHeight:'min-h',maxWidth:'max-w',maxHeight:'max-h',top:'top',bottom:'bottom',left:'left',right:'right',borderRadius:'rounded',borderTopLeftRadius:'rounded-tl',borderTopRightRadius:'rounded-tr',borderBottomLeftRadius:'rounded-bl',borderBottomRightRadius:'rounded-br',borderWidth:'border',borderTopWidth:'border-t',borderBottomWidth:'border-b',borderLeftWidth:'border-l'};
const named={flexDirection:{row:'flex-row',column:'flex-col'},alignItems:{center:'items-center','flex-start':'items-start','flex-end':'items-end',stretch:'items-stretch'},justifyContent:{center:'justify-center','space-between':'justify-between','flex-start':'justify-start','flex-end':'justify-end','space-around':'justify-around'},flexWrap:{wrap:'flex-wrap'},alignSelf:{center:'self-center','flex-start':'self-start'},overflow:{hidden:'overflow-hidden'},position:{absolute:'absolute',relative:'relative'},textAlign:{center:'text-center',right:'text-right',left:'text-left'},fontWeight:{400:'font-normal',500:'font-medium',600:'font-semibold',700:'font-semibold',800:'font-semibold',900:'font-semibold',bold:'font-semibold'},textTransform:{uppercase:'uppercase'}};
for(const file of ['src/screens/CarePanels.tsx','src/components/ChatBubble.tsx','src/components/ChatInput.tsx','src/components/AttachmentMenu.tsx','src/components/HistorySidebar.tsx','src/components/PatientModal.tsx']){
 let s=fs.readFileSync(file,'utf8');
 const a=ts.createSourceFile(file,s,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 const node=a.statements.find(n=>ts.isVariableStatement(n)&&n.declarationList.declarations[0].name.getText(a)==='styles');
 if(!node||!node.declarationList.declarations[0].initializer.arguments)continue;
 const literal=node.declarationList.declarations[0].initializer.arguments[0].getText(a);
 const obj=vm.runInNewContext('('+literal+')',{StyleSheet:{hairlineWidth:0.5},SIDEBAR_W:320,SCREEN_HEIGHT:800});
 const lines=[];
 for(const [key,value] of Object.entries(obj)){
   const classes=[],extra={};
   for(let [prop,v] of Object.entries(value)){
    if(prop==='borderRadius'&&v===8)v=20;
    if(prop==='fontSize'&&v<12)v=12;
    if(named[prop]?.[v])classes.push(named[prop][v]);
    else if(prop==='flex'&&v===1)classes.push('flex-1');
    else if(prop==='opacity')classes.push('opacity-'+Math.round(v*100));
    else if(prop==='fontSize')classes.push(`text-[${v}px]`);
    else if(prop==='lineHeight')classes.push(`leading-[${v}px]`);
    else if(prop==='letterSpacing')classes.push(`tracking-[${v}px]`);
    else if(['backgroundColor','color','borderColor','borderBottomColor','borderTopColor'].includes(prop)&&typeof v==='string'&&!v.startsWith('rgba')){
      const prefix=prop==='backgroundColor'?'bg':prop==='color'?'text':prop==='borderBottomColor'?'border-b':prop==='borderTopColor'?'border-t':'border';
      classes.push(prefix+'-'+(palette[v]||`[${v}]`));
    }else if(dim[prop])classes.push(`${dim[prop]}-[${v}${typeof v==='number'?'px':''}]`);
    else extra[prop]=v;
   }
   lines.push(`  ${key}: tw.style('${classes.join(' ')}'${Object.keys(extra).length?', '+JSON.stringify(extra):''}),`);
 }
 s=s.slice(0,node.getStart(a))+`const styles = {\n${lines.join('\n')}\n};`+s.slice(node.end);
 s="import tw from '../ui/tw';\n"+s;
 fs.writeFileSync(file,s);
}
