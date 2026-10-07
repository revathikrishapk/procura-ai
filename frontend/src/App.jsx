import { useEffect, useMemo, useState } from 'react'
import './App.css'

const API_BASE = 'http://localhost:8000'

async function apiFetch(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })

  const text = await response.text()
  const payload = text ? JSON.parse(text) : null

  if (!response.ok) {
    const detail = payload?.detail || payload?.message
    throw new Error(
      typeof detail === 'string' ? detail : JSON.stringify(detail || 'Request failed'),
    )
  }

  return payload
}

async function fetchWorkspaceData() {
  const [
    companies,
    products,
    suppliers,
    cases,
    quotes,
    approvals,
    purchaseOrders,
    deliveries,
  ] = await Promise.all([
    apiFetch('/companies'),
    apiFetch('/products'),
    apiFetch('/suppliers'),
    apiFetch('/cases'),
    apiFetch('/quotes'),
    apiFetch('/approvals'),
    apiFetch('/purchase-orders'),
    apiFetch('/deliveries'),
  ])
  const workflows = await Promise.all(
    cases.map((caseItem) => apiFetch(`/cases/${caseItem.id}/workflow`)),
  )

  return {
    companies,
    products,
    suppliers,
    cases,
    quotes,
    approvals,
    purchaseOrders,
    deliveries,
    workflows,
  }
}

function formatCurrency(value, currency = 'INR') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '—'
  }

  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(Number(value))
}

function App() {
  const [companies, setCompanies] = useState([])
  const [products, setProducts] = useState([])
  const [suppliers, setSuppliers] = useState([])
  const [cases, setCases] = useState([])
  const [quotes, setQuotes] = useState([])
  const [approvals, setApprovals] = useState([])
  const [purchaseOrders, setPurchaseOrders] = useState([])
  const [deliveries, setDeliveries] = useState([])
  const [workflows, setWorkflows] = useState([])
  const [retryingCaseId, setRetryingCaseId] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [companyForm, setCompanyForm] = useState({ name: '' })
  const [productForm, setProductForm] = useState({
    company_id: '',
    name: '',
    category: '',
    description: '',
  })
  const [supplierForm, setSupplierForm] = useState({
    company_id: '',
    name: '',
    email: '',
    website: '',
  })
  const [caseForm, setCaseForm] = useState({
    company_id: '',
    requested_by: '',
    product_name: '',
    quantity: '1',
    budget: '',
    description: '',
  })

  const loadData = async () => {
    try {
      const data = await fetchWorkspaceData()
      setCompanies(data.companies)
      setProducts(data.products)
      setSuppliers(data.suppliers)
      setCases(data.cases)
      setQuotes(data.quotes)
      setApprovals(data.approvals)
      setPurchaseOrders(data.purchaseOrders)
      setDeliveries(data.deliveries)
      setWorkflows(data.workflows)
      setError('')
    } catch (loadError) {
      setError(loadError.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let active = true
    fetchWorkspaceData()
      .then((data) => {
        if (!active) return
        setCompanies(data.companies)
        setProducts(data.products)
        setSuppliers(data.suppliers)
        setCases(data.cases)
        setQuotes(data.quotes)
        setApprovals(data.approvals)
        setPurchaseOrders(data.purchaseOrders)
        setDeliveries(data.deliveries)
        setWorkflows(data.workflows)
        setError('')
      })
      .catch((loadError) => {
        if (active) setError(loadError.message)
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [])

  const stats = useMemo(() => {
    const totalSpend = cases.reduce((sum, current) => sum + (Number(current.budget) || 0), 0)

    return [
      { label: 'Companies', value: companies.length },
      { label: 'Products', value: products.length },
      { label: 'Suppliers', value: suppliers.length },
      { label: 'Pending approvals', value: approvals.filter((approval) => approval.status === 'PENDING').length },
      { label: 'Budget tracked', value: formatCurrency(totalSpend) },
    ]
  }, [companies, products, suppliers, cases, approvals])

  const handleCompanySubmit = async (event) => {
    event.preventDefault()
    try {
      await apiFetch('/companies', {
        method: 'POST',
        body: JSON.stringify({ name: companyForm.name }),
      })
      setCompanyForm({ name: '' })
      await loadData()
    } catch (submitError) {
      setError(submitError.message)
    }
  }

  const handleProductSubmit = async (event) => {
    event.preventDefault()
    try {
      await apiFetch('/products', {
        method: 'POST',
        body: JSON.stringify({
          company_id: productForm.company_id,
          name: productForm.name,
          category: productForm.category,
          description: productForm.description,
        }),
      })
      setProductForm({ company_id: '', name: '', category: '', description: '' })
      await loadData()
    } catch (submitError) {
      setError(submitError.message)
    }
  }

  const handleSupplierSubmit = async (event) => {
    event.preventDefault()
    try {
      await apiFetch('/suppliers', {
        method: 'POST',
        body: JSON.stringify({
          company_id: supplierForm.company_id,
          name: supplierForm.name,
          email: supplierForm.email || null,
          website: supplierForm.website || null,
        }),
      })
      setSupplierForm({ company_id: '', name: '', email: '', website: '' })
      await loadData()
    } catch (submitError) {
      setError(submitError.message)
    }
  }

  const handleCaseSubmit = async (event) => {
    event.preventDefault()
    try {
      await apiFetch('/cases', {
        method: 'POST',
        body: JSON.stringify({
          company_id: caseForm.company_id,
          requested_by: caseForm.requested_by || null,
          product_name: caseForm.product_name,
          quantity: Number(caseForm.quantity),
          budget: Number(caseForm.budget),
          description: caseForm.description || null,
        }),
      })
      setCaseForm({
        company_id: '',
        requested_by: '',
        product_name: '',
        quantity: '1',
        budget: '',
        description: '',
      })
      await loadData()
    } catch (submitError) {
      const message = submitError.message
      await loadData()
      setError(message)
    }
  }

  const decideApproval = async (approval, decision) => {
    const reviewer = window.prompt(`Name of person ${decision === 'approve' ? 'approving' : 'rejecting'} this request:`)
    if (!reviewer?.trim()) return

    try {
      await apiFetch(`/approvals/${approval.id}/${decision}`, {
        method: 'PATCH',
        body: JSON.stringify({ approved_by: reviewer.trim() }),
      })
      await loadData()
    } catch (actionError) {
      setError(actionError.message)
    }
  }

  const retrySourcing = async (caseId) => {
    try {
      setRetryingCaseId(caseId)
      await apiFetch(`/cases/${caseId}/source`, { method: 'POST' })
      await loadData()
    } catch (retryError) {
      const message = retryError.message
      await loadData()
      setError(message)
    } finally {
      setRetryingCaseId('')
    }
  }

  const updateRecordStatus = async (path) => {
    try {
      await apiFetch(path, { method: 'PATCH' })
      await loadData()
    } catch (actionError) {
      setError(actionError.message)
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Procurement workspace</p>
          <h1>Procura AI</h1>
        </div>
        <button className="primary-button" type="button" onClick={loadData}>
          Refresh data
        </button>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <section className="stats-grid">
        {stats.map((stat) => (
          <article key={stat.label} className="stat-card">
            <span>{stat.label}</span>
            <strong>{stat.value}</strong>
          </article>
        ))}
      </section>

      {loading ? (
        <div className="loading-state">Loading workspace…</div>
      ) : (
        <>
          <div className="panel-grid">
            <section className="panel">
              <h2>Create company</h2>
              <form onSubmit={handleCompanySubmit} className="stack-form">
                <input
                  value={companyForm.name}
                  onChange={(event) => setCompanyForm({ name: event.target.value })}
                  placeholder="Company name"
                />
                <button type="submit" className="primary-button">Save company</button>
              </form>
            </section>

            <section className="panel">
              <h2>New product</h2>
              <form onSubmit={handleProductSubmit} className="stack-form">
                <select
                  value={productForm.company_id}
                  onChange={(event) => setProductForm({ ...productForm, company_id: event.target.value })}
                >
                  <option value="">Select company</option>
                  {companies.map((company) => (
                    <option key={company.id} value={company.id}>
                      {company.name}
                    </option>
                  ))}
                </select>
                <input
                  value={productForm.name}
                  onChange={(event) => setProductForm({ ...productForm, name: event.target.value })}
                  placeholder="Product name"
                />
                <input
                  value={productForm.category}
                  onChange={(event) => setProductForm({ ...productForm, category: event.target.value })}
                  placeholder="Category"
                />
                <textarea
                  value={productForm.description}
                  onChange={(event) => setProductForm({ ...productForm, description: event.target.value })}
                  placeholder="Description"
                  rows="3"
                />
                <button type="submit" className="primary-button">Add product</button>
              </form>
            </section>

            <section className="panel">
              <h2>New supplier</h2>
              <form onSubmit={handleSupplierSubmit} className="stack-form">
                <select
                  value={supplierForm.company_id}
                  onChange={(event) => setSupplierForm({ ...supplierForm, company_id: event.target.value })}
                >
                  <option value="">Select company</option>
                  {companies.map((company) => (
                    <option key={company.id} value={company.id}>
                      {company.name}
                    </option>
                  ))}
                </select>
                <input
                  value={supplierForm.name}
                  onChange={(event) => setSupplierForm({ ...supplierForm, name: event.target.value })}
                  placeholder="Supplier name"
                />
                <input
                  value={supplierForm.email}
                  onChange={(event) => setSupplierForm({ ...supplierForm, email: event.target.value })}
                  placeholder="Email"
                />
                <input
                  value={supplierForm.website}
                  onChange={(event) => setSupplierForm({ ...supplierForm, website: event.target.value })}
                  placeholder="Website"
                />
                <button type="submit" className="primary-button">Add supplier</button>
              </form>
            </section>

            <section className="panel">
              <h2>New case</h2>
              <form onSubmit={handleCaseSubmit} className="stack-form">
                <select
                  required
                  value={caseForm.company_id}
                  onChange={(event) => setCaseForm({ ...caseForm, company_id: event.target.value })}
                >
                  <option value="">Select company</option>
                  {companies.map((company) => (
                    <option key={company.id} value={company.id}>
                      {company.name}
                    </option>
                  ))}
                </select>
                <input
                  value={caseForm.requested_by}
                  onChange={(event) => setCaseForm({ ...caseForm, requested_by: event.target.value })}
                  placeholder="Requested by"
                />
                <input
                  required
                  value={caseForm.product_name}
                  onChange={(event) => setCaseForm({ ...caseForm, product_name: event.target.value })}
                  placeholder="Product name"
                />
                <div className="inline-fields">
                  <input
                    type="number"
                    min="1"
                    required
                    value={caseForm.quantity}
                    onChange={(event) => setCaseForm({ ...caseForm, quantity: event.target.value })}
                    placeholder="Quantity"
                  />
                  <input
                    type="number"
                    min="0.01"
                    step="any"
                    required
                    value={caseForm.budget}
                    onChange={(event) => setCaseForm({ ...caseForm, budget: event.target.value })}
                    placeholder="Budget"
                  />
                </div>
                <textarea
                  value={caseForm.description}
                  onChange={(event) => setCaseForm({ ...caseForm, description: event.target.value })}
                  placeholder="Purpose / notes"
                  rows="3"
                />
                <button type="submit" className="primary-button">Create case</button>
              </form>
            </section>
          </div>

          <section className="panel panel-wide">
            <h2>Procurement pipeline</h2>
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Product</th>
                    <th>Company</th>
                    <th>Qty</th>
                    <th>Status</th>
                    <th>Stage</th>
                    <th>Budget</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {cases.map((caseItem) => (
                    <tr key={caseItem.id}>
                      <td>{caseItem.id}</td>
                      <td>{caseItem.product_name}</td>
                      <td>{caseItem.company_id}</td>
                      <td>{caseItem.quantity}</td>
                      <td>
                        <span className="status-pill">{caseItem.status}</span>
                      </td>
                      <td>{caseItem.current_stage}</td>
                      <td>{formatCurrency(caseItem.budget, caseItem.currency)}</td>
                      <td>
                        {['SOURCING_FAILED', 'NO_MATCHING_OFFERS'].includes(caseItem.status) && (
                          <button
                            type="button"
                            className="small-button approve-button"
                            disabled={retryingCaseId === caseItem.id}
                            onClick={() => retrySourcing(caseItem.id)}
                          >
                            {retryingCaseId === caseItem.id ? 'Retrying…' : 'Retry sourcing'}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel panel-wide">
            <h2>Agent workflow runs</h2>
            {workflows.length === 0 ? (
              <p className="empty-state">Submit a procurement request to start the agent workflow.</p>
            ) : (
              <div className="workflow-run-list">
                {workflows.map((workflow) => {
                  const caseItem = cases.find((current) => current.id === workflow.case_id)
                  const state = workflow.state || {}
                  const completedStages = new Set(
                    (workflow.history || []).map((event) => event.stage),
                  )
                  const agentStages = [
                    ['INTAKE', 'Intake'],
                    ['SOURCING', 'Supplier sourcing'],
                    ['SUPPLIER_EVALUATION', 'Supplier evaluation'],
                    ['QUOTATION_ANALYSIS', 'Quotation analysis'],
                    ['NEGOTIATION', 'Negotiation / RFQ draft'],
                    ['APPROVAL', 'Human approval'],
                    ['PURCHASE_ORDER', 'Purchase order'],
                    ['DELIVERY_TRACKING', 'Delivery tracking'],
                  ]
                  return (
                    <details className="workflow-run" key={workflow.case_id}>
                      <summary>
                        <span>
                          <strong>{caseItem?.product_name || workflow.case_id}</strong>
                          <small>{workflow.case_id} · {workflow.current_stage || 'Workflow state unavailable'}</small>
                        </span>
                        <span className="status-pill">{workflow.status || caseItem?.status || 'UNKNOWN'}</span>
                      </summary>
                      <div className="workflow-run-content">
                        <div className="workflow-agent-list">
                          {agentStages.map(([stage, label]) => {
                            const isCurrent = workflow.current_stage === stage
                            const isComplete = completedStages.has(stage) && !isCurrent
                            return (
                              <span
                                className={isCurrent ? 'is-current' : isComplete ? 'is-complete' : ''}
                                key={stage}
                              >
                                {isComplete ? 'Done · ' : isCurrent ? 'Current · ' : ''}{label}
                              </span>
                            )
                          })}
                        </div>
                        {state.error && <p className="error-inline">{state.error}</p>}
                        {state.tracking_status && (
                          <p className="tracking-note">
                            Delivery tracking: {state.tracking_status} · {state.tracking_provider}
                            {state.tracking_reference ? ` · ${state.tracking_reference}` : ''}
                          </p>
                        )}
                        {state.supplier_evaluations?.length > 0 && (
                          <div className="table-wrapper">
                            <table>
                              <thead>
                                <tr>
                                  <th>Supplier</th>
                                  <th>Offer total</th>
                                  <th>Score / 100</th>
                                  <th>Verification</th>
                                  <th>Evidence</th>
                                </tr>
                              </thead>
                              <tbody>
                                {state.supplier_evaluations.map((offer) => (
                                  <tr key={`${workflow.case_id}-${offer.supplier_name}`}>
                                    <td>{offer.supplier_name}</td>
                                    <td>{formatCurrency(offer.total_price, offer.currency)}</td>
                                    <td>{offer.evaluation_score}</td>
                                    <td>{offer.verification_status}</td>
                                    <td>
                                      {offer.source && offer.source.startsWith('http')
                                        ? <a className="source-link" href={offer.source} target="_blank" rel="noreferrer">Source</a>
                                        : 'Company catalog'}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                        {state.negotiation_drafts?.length > 0 && (
                          <div className="draft-list">
                            <h3>RFQ / negotiation drafts (not sent)</h3>
                            {state.negotiation_drafts.map((draft) => (
                              <article className="draft-card" key={draft.rfq_id}>
                                <strong>{draft.supplier_name} · {draft.rfq_id}</strong>
                                <p>{draft.subject}</p>
                                <p>{draft.body}</p>
                                <small>Adapter: {draft.provider} · {draft.delivery_status}</small>
                              </article>
                            ))}
                          </div>
                        )}
                        {workflow.history?.length > 0 && (
                          <div className="audit-list">
                            <h3>Execution history</h3>
                            {workflow.history.map((event) => (
                              <p key={event.id}>
                                <strong>{event.stage}</strong> · {event.event_type}
                              </p>
                            ))}
                          </div>
                        )}
                        {workflow.paused_for_approval && (
                          <p className="approval-note">Paused at the LangGraph human-approval interrupt. Approve or reject it in the Approval queue.</p>
                        )}
                      </div>
                    </details>
                  )
                })}
              </div>
            )}
          </section>

          <div className="data-grid workflow-grid">
            <section className="panel">
              <h2>Approval queue</h2>
              {approvals.filter((approval) => approval.status === 'PENDING').length === 0 ? (
                <p className="empty-state">No requests waiting for approval.</p>
              ) : (
                <ul className="list-stack">
                  {approvals.filter((approval) => approval.status === 'PENDING').map((approval) => {
                    const caseItem = cases.find((current) => current.id === approval.case_id)
                    return (
                      <li key={approval.id}>
                        <strong>{caseItem?.product_name || approval.case_id}</strong>
                        <span>{approval.id} · {formatCurrency(approval.amount, approval.currency)}</span>
                        <div className="approval-actions">
                          <button type="button" className="small-button approve-button" onClick={() => decideApproval(approval, 'approve')}>Approve & create PO</button>
                          <button type="button" className="small-button reject-button" onClick={() => decideApproval(approval, 'reject')}>Reject</button>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              )}
            </section>

            <section className="panel">
              <h2>Selected offers</h2>
              {quotes.length === 0 ? (
                <p className="empty-state">Offers appear here after you submit a request.</p>
              ) : (
                <ul className="list-stack">
                  {quotes.map((quote) => (
                    <li key={quote.id}>
                      <strong>{quote.product_name} · {formatCurrency(quote.total_price, quote.currency)}</strong>
                      <span>{quote.status} · {quote.quantity} units · {quote.currency}</span>
                      {quote.notes?.startsWith('Source: http') && (
                        <a className="source-link" href={quote.notes.split('\n')[0].slice(8)} target="_blank" rel="noreferrer">View source</a>
                      )}
                      {quote.notes?.includes('Price evidence:') && (
                        <span>{quote.notes.split('Price evidence: ')[1]?.split('\n')[0]}</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="panel">
              <h2>Purchase orders</h2>
              {purchaseOrders.length === 0 ? (
                <p className="empty-state">A PO is created after an approval is granted.</p>
              ) : (
                <ul className="list-stack">
                  {purchaseOrders.map((purchaseOrder) => (
                    <li key={purchaseOrder.id}>
                      <div style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px'}}>
                        <div>
                          <strong>{purchaseOrder.id} · {purchaseOrder.product_name}</strong>
                          <div className="muted">{purchaseOrder.status} · {formatCurrency(purchaseOrder.total_amount, purchaseOrder.currency)}</div>
                        </div>
                        <div style={{display: 'flex', gap: '8px'}}>
                          <button
                            type="button"
                            className="small-button"
                            onClick={() => window.open(`${API_BASE}/purchase-orders/${purchaseOrder.id}/pdf`, '_blank')}
                          >
                            View PO
                          </button>
                          {purchaseOrder.status === 'APPROVED' && (
                            <button
                              type="button"
                              className="small-button approve-button"
                              onClick={() => updateRecordStatus(`/purchase-orders/${purchaseOrder.id}/status?new_status=ISSUED`)}
                            >
                              Mark PO issued
                            </button>
                          )}
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="panel">
              <h2>Delivery tracking</h2>
              {deliveries.length === 0 ? (
                <p className="empty-state">Tracking starts after approval creates a purchase order.</p>
              ) : (
                <ul className="list-stack">
                  {deliveries.map((delivery) => (
                    <li key={delivery.id}>
                      <strong>{delivery.po_id}</strong>
                      <span>
                        {delivery.status}
                        {delivery.expected_delivery_date
                          ? ` · expected ${delivery.expected_delivery_date}`
                          : ''}
                      </span>
                      {delivery.status === 'PENDING' && (
                        <button
                          type="button"
                          className="small-button approve-button"
                          onClick={() => updateRecordStatus(`/deliveries/${delivery.id}/status?new_status=IN_TRANSIT`)}
                        >
                          Mark in transit
                        </button>
                      )}
                      {delivery.status === 'IN_TRANSIT' && (
                        <button
                          type="button"
                          className="small-button approve-button"
                          onClick={() => updateRecordStatus(`/deliveries/${delivery.id}/status?new_status=DELIVERED`)}
                        >
                          Mark delivered
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          <div className="data-grid">
            <section className="panel">
              <h2>Companies</h2>
              <ul className="list-stack">
                {companies.map((company) => (
                  <li key={company.id}>
                    <strong>{company.name}</strong>
                    <span>{company.id}</span>
                  </li>
                ))}
              </ul>
            </section>

            <section className="panel">
              <h2>Products</h2>
              <ul className="list-stack">
                {products.map((product) => (
                  <li key={product.id}>
                    <strong>{product.name}</strong>
                    <span>{product.category || 'General'}</span>
                  </li>
                ))}
              </ul>
            </section>

            <section className="panel">
              <h2>Suppliers</h2>
              <ul className="list-stack">
                {suppliers.map((supplier) => (
                  <li key={supplier.id}>
                    <strong>{supplier.name}</strong>
                    <span>{supplier.website || supplier.email || 'No contact'}</span>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </>
      )}
    </div>
  )
}

export default App
