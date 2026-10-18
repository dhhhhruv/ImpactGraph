import React, { useEffect, useRef, useMemo, useState } from 'react'

const CY_STYLE = [
  {
    selector: 'node',
    style: {
      'label': 'data(label)',
      'text-valign': 'bottom',
      'text-halign': 'center',
      'font-size': 10,
      'font-family': 'JetBrains Mono, monospace',
      'color': '#8b92a8',
      'text-opacity': 0,
      'background-color': '#252a38',
      'border-width': 1.5,
      'border-color': '#2e3448',
      'width': 28,
      'height': 28,
      'text-margin-y': 4,
      'min-zoomed-font-size': 8,
    },
  },
  {
    selector: 'node[type="changed"], node:selected, node.highlighted',
    style: { 'text-opacity': 1 },
  },
  {
    selector: 'node[type="changed"]',
    style: {
      'background-color': '#f87171',
      'border-color': '#f87171',
      'border-width': 2,
      'color': '#e8eaf0',
      'font-weight': 700,
    },
  },
  {
    selector: 'node[type="caller"]',
    style: {
      'background-color': '#fb923c',
      'border-color': '#fb923c',
      'color': '#e8eaf0',
    },
  },
  {
    selector: 'node[type="test"]',
    style: {
      'background-color': '#34d399',
      'border-color': '#34d399',
      'color': '#0a0b0f',
      'font-weight': 600,
      'shape': 'diamond',
    },
  },
  {
    selector: 'node[type="reviewer"]',
    style: {
      'background-color': '#a78bfa',
      'border-color': '#a78bfa',
      'shape': 'ellipse',
      'color': '#0a0b0f',
    },
  },
  {
    selector: 'node.dimmed',
    style: { 'opacity': 0.2 },
  },
  {
    selector: 'node.highlighted',
    style: { 'border-width': 3, 'border-color': '#4f8ef7' },
  },
  {
    selector: 'edge',
    style: {
      'width': 1.5,
      'line-color': '#2e3448',
      'target-arrow-color': '#2e3448',
      'target-arrow-shape': 'vee',
      'curve-style': 'bezier',
      'arrow-scale': 0.8,
    },
  },
  {
    selector: 'edge[type="evidence"]',
    style: {
      'width': 3,
      'line-color': '#4f8ef7',
      'target-arrow-color': '#4f8ef7',
    },
  },
  {
    selector: 'edge.dimmed',
    style: { 'opacity': 0.1 },
  },
  {
    selector: ':selected',
    style: {
      'border-color': '#4f8ef7',
      'border-width': 3,
      'line-color': '#4f8ef7',
      'target-arrow-color': '#4f8ef7',
    },
  },
]

const MAX_NODES = 150

export default function GraphCanvas({ elements, selectedNodeId, onNodeClick }) {
  const containerRef = useRef(null)
  const cyRef = useRef(null)
  const [nodeCount, setNodeCount] = useState(0)
  const [showMore, setShowMore] = useState(false)

  const capped = useMemo(() => {
    if (!elements) return { nodes: [], edges: [] }
    const nodes = elements.nodes || []
    const edges = elements.edges || []
    const shown = showMore ? nodes : nodes.slice(0, MAX_NODES)
    const shownIds = new Set(shown.map(n => n.data.id))
    const shownEdges = edges.filter(e => shownIds.has(e.data.source) && shownIds.has(e.data.target))
    return { nodes: shown, edges: shownEdges, total: nodes.length }
  }, [elements, showMore])

  useEffect(() => {
    setNodeCount(capped.total || 0)
  }, [capped.total])

  useEffect(() => {
    if (!containerRef.current) return
    let cy
    const initCy = async () => {
      const cytoscape = (await import('cytoscape')).default
      let fcose
      try { fcose = (await import('cytoscape-fcose')).default; cytoscape.use(fcose) } catch {}

      cy = cytoscape({
        container: containerRef.current,
        elements: [...capped.nodes, ...capped.edges],
        style: CY_STYLE,
        layout: {
          name: fcose ? 'fcose' : 'cose',
          animate: true,
          animationDuration: 500,
          randomize: true,
          nodeRepulsion: () => 9000,
        },
        minZoom: 0.2,
        maxZoom: 4,
      })

      cy.on('tap', 'node', evt => {
        const id = evt.target.data('id')
        onNodeClick && onNodeClick(id)
      })
      cy.on('tap', evt => {
        if (evt.target === cy) onNodeClick && onNodeClick(null)
      })

      cyRef.current = cy
    }
    initCy()
    return () => { if (cyRef.current) { cyRef.current.destroy(); cyRef.current = null } }
  }, [capped])

  // Highlight selected node
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.elements().removeClass('dimmed highlighted')
    if (selectedNodeId) {
      cy.elements().addClass('dimmed')
      const node = cy.$(`#${CSS.escape(selectedNodeId)}`)
      if (node.length) {
        const neighborhood = node.closedNeighborhood()
        neighborhood.removeClass('dimmed')
        node.addClass('highlighted')
      }
    }
  }, [selectedNodeId])

  const isEmpty = !capped.nodes.length

  if (isEmpty) {
    return (
      <div className="state-center">
        <div className="state-icon">⬡</div>
        <div className="state-title">No Graph Data</div>
        <div className="state-sub">Run an analysis to visualize the call graph and blast radius.</div>
      </div>
    )
  }

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      <div className="node-count-badge">
        {Math.min(capped.nodes.length, MAX_NODES)} / {nodeCount} nodes
      </div>
      {nodeCount > MAX_NODES && !showMore && (
        <button
          className="btn btn-ghost btn-sm"
          style={{ position: 'absolute', top: 12, left: '50%', transform: 'translateX(-50%)' }}
          onClick={() => setShowMore(true)}
        >
          Show all {nodeCount} nodes
        </button>
      )}
      <div className="graph-legend">
        {[
          { color: 'var(--node-changed)',  label: 'Changed' },
          { color: 'var(--node-caller)',   label: 'Affected caller' },
          { color: 'var(--node-test)',     label: 'Test' },
          
          { color: 'var(--node-evidence)', label: 'Evidence path' },
        ].map(l => (
          <div key={l.label} className="legend-item">
            <div className="legend-dot" style={{ background: l.color }} />
            {l.label}
          </div>
        ))}
      </div>
    </div>
  )
}
