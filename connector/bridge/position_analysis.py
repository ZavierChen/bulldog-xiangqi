"""Format existing engine telemetry; no search, models or estimated substitutes."""
def format_analysis(evaluation,side):
    if not evaluation or side not in ('w','b'):
        return ('红方：评分暂无｜胜率暂无','黑方：评分暂无｜胜率暂无')
    red_score=evaluation['score']*(1 if side=='w' else -1)
    wdl=evaluation.get('wdl')
    if wdl and (len(wdl)!=3 or any(v<0 for v in wdl) or sum(wdl)!=1000):wdl=None
    red_wdl=wdl if side=='w' or not wdl else list(reversed(wdl))
    def row(name,score,values):
        if evaluation['score_type']=='mate':
            text=f'预计 {abs(score)} 步将死对方' if score>0 else f'预计 {abs(score)} 步被将死'
        else:text=f'评分 {score/100:+.2f}'
        probabilities=f'胜 {values[0]/10:.1f}%｜和 {values[1]/10:.1f}%｜负 {values[2]/10:.1f}%' if values else '胜率暂无'
        return f'{name}：{text}｜{probabilities}'
    return (row('红方',red_score,red_wdl),row('黑方',-red_score,list(reversed(red_wdl)) if red_wdl else None))
