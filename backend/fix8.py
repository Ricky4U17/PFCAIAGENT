c = open('../frontend/src/components/ChannelSelect.tsx', encoding='utf-8').read()

# Remove the green L formula card
start1 = c.find('<Card style={{marginBottom:11,background:C.greenL')
end1 = c.find('</Card>', start1) + len('</Card>')
c = c[:start1] + c[end1:]

# Remove the amber analog IC card
start2 = c.find('{isAnalog && (')
end2 = c.find(')}', start2) + len(')}')
c = c[:start2] + c[end2:]

open('../frontend/src/components/ChannelSelect.tsx', 'w', encoding='utf-8').write(c)
print('Done')