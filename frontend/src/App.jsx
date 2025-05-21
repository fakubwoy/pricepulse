function App() {
  return (
    <div className="p-4">
      <h1 className="text-xl font-bold">PricePulse</h1>
      <input
        type="text"
        placeholder="Enter Amazon Product URL"
        className="border p-2 w-full mt-4"
      />
      <button className="bg-blue-600 text-white px-4 py-2 mt-2 rounded">
        Start Tracking
      </button>
    </div>
  )
}
export default App;
